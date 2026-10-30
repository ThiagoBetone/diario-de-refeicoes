"""API de refeições. Execute: python -m uvicorn main:app --reload."""

from contextlib import asynccontextmanager, closing
from datetime import date, time
from pathlib import Path
import sqlite3
import json
import unicodedata
from decimal import Decimal, ROUND_HALF_UP

from fastapi import FastAPI, HTTPException, Query, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, model_validator
from energia import preparar_energia, registrar_rotas_energia

ROOT = Path(__file__).resolve().parent
NUTRIENTES = ("calorias", "proteinas", "carboidratos", "gorduras")


def normalizar(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto.casefold()) if not unicodedata.combining(c))


class AlimentoEntrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", allow_inf_nan=False)
    nome: str = Field(min_length=1, max_length=120)
    calorias: float = Field(ge=0, le=10000, description="kcal por 100 g")
    proteinas: float = Field(ge=0, le=100, description="g por 100 g")
    carboidratos: float = Field(ge=0, le=100, description="g por 100 g")
    gorduras: float = Field(ge=0, le=100, description="g por 100 g")
    peso_unidade_gramas: float | None = Field(default=None, gt=0, le=10000, description="Peso comestível de uma unidade em gramas")


class Alimento(AlimentoEntrada):
    id: int
    fonte: str | None = None
    codigo_fonte: str | None = None
    url_fonte: str | None = None
    coletado_em: str | None = None
    carboidratos_tipo: str | None = None


class ItemEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    alimento_id: int = Field(gt=0)
    quantidade_gramas: float | None = Field(default=None, gt=0, le=10000)
    quantidade_unidades: float | None = Field(default=None, gt=0, le=10000)
    peso_unidade_gramas: float | None = Field(default=None, gt=0, le=10000)

    @model_validator(mode="after")
    def validar_medida(self):
        if (self.quantidade_gramas is None) == (self.quantidade_unidades is None):
            raise ValueError("Informe gramas ou unidades, exclusivamente")
        if self.quantidade_unidades is None and self.peso_unidade_gramas is not None:
            raise ValueError("Peso por unidade só pode ser usado com unidades")
        return self


class RefeicaoComAlimentos(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")
    nome: str = Field(min_length=1, max_length=120, examples=["Café da manhã"])
    data: date
    horario: time = time(12, 0)
    itens: list[ItemEntrada] = Field(min_length=1, max_length=100)


class ItemConsumido(BaseModel):
    alimento_id: int
    quantidade_gramas: float
    quantidade_unidades: float | None = None
    peso_unidade_gramas: float | None = None
    nome: str
    calorias: float
    proteinas: float
    carboidratos: float
    gorduras: float


class RefeicaoEntrada(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid", allow_inf_nan=False)

    nome: str = Field(min_length=1, max_length=120, examples=["Almoço"])
    data: date = Field(description="Data local em que a refeição foi consumida.")
    horario: time = Field(default=time(12, 0), description="Horário da refeição.")
    calorias: float = Field(ge=0, le=100000, description="Total da porção consumida, em kcal.")
    proteinas: float = Field(ge=0, le=10000, description="Total da porção consumida, em gramas.")
    carboidratos: float = Field(ge=0, le=10000, description="Total da porção consumida, em gramas.")
    gorduras: float = Field(ge=0, le=10000, description="Total da porção consumida, em gramas.")


class Refeicao(RefeicaoEntrada):
    id: int
    calorias: float = Field(ge=0)
    proteinas: float = Field(ge=0)
    carboidratos: float = Field(ge=0)
    gorduras: float = Field(ge=0)
    itens: list[ItemConsumido] = Field(default_factory=list)


class ResumoDiario(BaseModel):
    data: date
    quantidade_refeicoes: int
    calorias: float
    proteinas: float
    carboidratos: float
    gorduras: float


def preparar_catalogo(conn):
    colunas = {row[1] for row in conn.execute("PRAGMA table_info(alimentos)")}
    for coluna in ("fonte", "codigo_fonte", "url_fonte", "coletado_em", "carboidratos_tipo"):
        if coluna not in colunas:
            conn.execute(f"ALTER TABLE alimentos ADD COLUMN {coluna} TEXT")
    if "peso_unidade_gramas" not in colunas:
        conn.execute("ALTER TABLE alimentos ADD COLUMN peso_unidade_gramas REAL")
        # Medida média da parte comestível nas fichas TBCA consultadas.
        for codigo, peso in (("BRC0010J", 50), ("BRC0011C", 40), ("BRC0064C", 130)):
            conn.execute("UPDATE alimentos SET peso_unidade_gramas=? WHERE fonte='TBCA' AND codigo_fonte=?", (peso, codigo))
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS ix_alimentos_fonte ON alimentos(fonte, codigo_fonte)")


def create_app(db_path: str | Path = ROOT / "refeicoes.db") -> FastAPI:
    def conectar():
        conn = sqlite3.connect(str(db_path), timeout=10)
        conn.row_factory = sqlite3.Row
        conn.create_function("normalizar", 1, normalizar)
        return conn

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        with closing(conectar()) as conn, conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS refeicoes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nome TEXT NOT NULL, data TEXT NOT NULL, horario TEXT NOT NULL,
                    calorias REAL NOT NULL CHECK (calorias >= 0),
                    proteinas REAL NOT NULL CHECK (proteinas >= 0),
                    carboidratos REAL NOT NULL CHECK (carboidratos >= 0),
                    gorduras REAL NOT NULL CHECK (gorduras >= 0)
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS ix_refeicoes_data ON refeicoes(data)")
            if "itens" not in {row[1] for row in conn.execute("PRAGMA table_info(refeicoes)")}:
                conn.execute("ALTER TABLE refeicoes ADD COLUMN itens TEXT NOT NULL DEFAULT '[]'")
            conn.execute("""CREATE TABLE IF NOT EXISTS alimentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
                calorias REAL NOT NULL, proteinas REAL NOT NULL,
                carboidratos REAL NOT NULL, gorduras REAL NOT NULL
            )""")
            preparar_catalogo(conn)
            preparar_energia(conn)
        yield

    app = FastAPI(
        title="Diário de refeições", version="0.2.0", lifespan=lifespan,
        description="Cadastre os nutrientes da porção consumida e consulte os totais por data. "
        "Protótipo local de um único usuário. Calorias em kcal; macronutrientes em gramas.",
    )

    app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
    registrar_rotas_energia(app, conectar)

    @app.get("/", include_in_schema=False)
    def pagina():
        return FileResponse(ROOT / "static" / "index.html")

    @app.post("/alimentos", response_model=Alimento, status_code=201, tags=["Alimentos"])
    def cadastrar_alimento(alimento: AlimentoEntrada):
        dados = alimento.model_dump()
        with closing(conectar()) as conn, conn:
            cursor = conn.execute("""INSERT INTO alimentos
                (nome, calorias, proteinas, carboidratos, gorduras, peso_unidade_gramas)
                VALUES (:nome, :calorias, :proteinas, :carboidratos, :gorduras, :peso_unidade_gramas)""", dados)
            return {"id": cursor.lastrowid, **dados}

    @app.get("/alimentos", response_model=list[Alimento], tags=["Alimentos"])
    def pesquisar_alimentos(busca: str = Query(default="", max_length=120)):
        with closing(conectar()) as conn:
            return [dict(row) for row in conn.execute(
                "SELECT * FROM alimentos WHERE instr(normalizar(nome), ?) > 0 ORDER BY nome, id",
                (normalizar(busca.strip()),))]

    @app.post("/refeicoes", response_model=Refeicao, status_code=201, tags=["Refeições"])
    def cadastrar(refeicao: RefeicaoComAlimentos | RefeicaoEntrada):
        dados = refeicao.model_dump(mode="json")
        with closing(conectar()) as conn, conn:
            itens = []
            if isinstance(refeicao, RefeicaoComAlimentos):
                totais = {campo: Decimal(0) for campo in NUTRIENTES}
                for item in refeicao.itens:
                    alimento = conn.execute("SELECT * FROM alimentos WHERE id = ?", (item.alimento_id,)).fetchone()
                    if alimento is None:
                        raise HTTPException(404, f"Alimento {item.alimento_id} não encontrado")
                    peso = None
                    if item.quantidade_unidades is not None:
                        peso = item.peso_unidade_gramas or alimento["peso_unidade_gramas"]
                        if peso is None:
                            raise HTTPException(422, "Informe o peso comestível por unidade desse alimento")
                        quantidade = Decimal(str(item.quantidade_unidades)) * Decimal(str(peso))
                    else:
                        quantidade = Decimal(str(item.quantidade_gramas))
                    if quantidade > 10000:
                        raise HTTPException(422, "O peso total de um item não pode ultrapassar 10000 g")
                    valores = {campo: Decimal(str(alimento[campo])) * quantidade / 100
                               for campo in NUTRIENTES}
                    for campo, valor in valores.items():
                        totais[campo] += valor
                    itens.append({**item.model_dump(), "quantidade_gramas": float(quantidade),
                                  "peso_unidade_gramas": peso, "nome": alimento["nome"],
                                  **{campo: float(valor) for campo, valor in valores.items()}})
                dados.update({campo: float(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
                              for campo, valor in totais.items()})
            dados["itens"] = json.dumps(itens, ensure_ascii=False)
            cursor = conn.execute(
                "INSERT INTO refeicoes (nome, data, horario, calorias, proteinas, carboidratos, gorduras, itens) "
                "VALUES (:nome, :data, :horario, :calorias, :proteinas, :carboidratos, :gorduras, :itens)", dados,
            )
            return {"id": cursor.lastrowid, **dados, "itens": itens}

    @app.get("/refeicoes", response_model=list[Refeicao], tags=["Refeições"])
    def listar(data: date = Query(description="Data local no formato AAAA-MM-DD")):
        with closing(conectar()) as conn:
            return [{**dict(row), "itens": json.loads(row["itens"])} for row in conn.execute(
                "SELECT * FROM refeicoes WHERE data = ? ORDER BY horario, id", (data.isoformat(),)
            )]

    @app.delete("/refeicoes/{refeicao_id}", status_code=204, tags=["Refeições"])
    def excluir(refeicao_id: int):
        with closing(conectar()) as conn, conn:
            result = conn.execute("DELETE FROM refeicoes WHERE id = ?", (refeicao_id,))
            if result.rowcount == 0:
                raise HTTPException(status_code=404, detail="Refeição não encontrada")
        return Response(status_code=204)

    @app.get("/resumo-diario", response_model=ResumoDiario, tags=["Resumo"])
    def resumo(data: date = Query(description="Data local no formato AAAA-MM-DD")):
        with closing(conectar()) as conn:
            row = conn.execute("""
                SELECT COUNT(*) AS quantidade_refeicoes,
                       ROUND(COALESCE(SUM(calorias), 0), 2) AS calorias,
                       ROUND(COALESCE(SUM(proteinas), 0), 2) AS proteinas,
                       ROUND(COALESCE(SUM(carboidratos), 0), 2) AS carboidratos,
                       ROUND(COALESCE(SUM(gorduras), 0), 2) AS gorduras
                FROM refeicoes WHERE data = ?
            """, (data.isoformat(),)).fetchone()
            return {"data": data, **dict(row)}

    return app


app = create_app()
