"""Perfil pessoal, estimativa de repouso e treinos do diário local."""
from contextlib import closing
from datetime import date
from typing import Literal

from fastapi import HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator


class PerfilEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    idade: int = Field(ge=18, le=100)
    peso_kg: float = Field(ge=20, le=400)
    altura_cm: float = Field(ge=100, le=250)
    sexo_formula: Literal["masculino", "feminino"]
    vigente_desde: date

    @model_validator(mode="after")
    def validar_resultado(self):
        if calcular_tmb(self) <= 0:
            raise ValueError("Esses dados não produzem uma estimativa positiva. Confira os campos.")
        return self


def calcular_tmb(perfil):
    ajuste = 5 if perfil.sexo_formula == "masculino" else -161
    return round(10 * perfil.peso_kg + 6.25 * perfil.altura_cm - 5 * perfil.idade + ajuste, 2)


class Perfil(PerfilEntrada):
    tmb: float


class TreinoEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True, allow_inf_nan=False)
    nome: str = Field(min_length=1, max_length=120)
    data: date
    calorias: float = Field(gt=0, le=10000, description="Calorias ativas estimadas do treino, em kcal")


class Treino(TreinoEntrada):
    id: int


class MedidaEntrada(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    data: date
    peso_kg: float | None = Field(default=None, ge=20, le=400)
    cintura_cm: float | None = Field(default=None, ge=30, le=300)

    @model_validator(mode="after")
    def pelo_menos_uma_medida(self):
        if self.peso_kg is None and self.cintura_cm is None:
            raise ValueError("Informe peso ou cintura")
        return self


class VisibilidadeRefeicao(BaseModel):
    model_config = ConfigDict(extra="forbid")
    excluida: bool = Field(strict=True)


class Balanco(BaseModel):
    data: date
    perfil: Perfil | None
    consumidas: float
    treinos: list[Treino]
    calorias_treinos: float
    referencia: float | None
    diferenca_tmb: float | None
    diferenca_referencia: float | None


def preparar_energia(conn):
    conn.execute("CREATE TABLE IF NOT EXISTS refeicoes_ocultas_evolucao (refeicao_id INTEGER PRIMARY KEY)")
    conn.execute("""CREATE TABLE IF NOT EXISTS medidas_pessoais (
        perfil_id INTEGER NOT NULL DEFAULT 1 CHECK(perfil_id=1),
        data TEXT NOT NULL, peso_kg REAL, cintura_cm REAL,
        PRIMARY KEY(perfil_id, data)
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS perfil_pessoal (
        vigente_desde TEXT PRIMARY KEY, idade INTEGER NOT NULL, peso_kg REAL NOT NULL,
        altura_cm REAL NOT NULL, sexo_formula TEXT NOT NULL, tmb REAL NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS treinos (
        id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL,
        data TEXT NOT NULL, calorias REAL NOT NULL CHECK(calorias > 0)
    )""")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_treinos_data ON treinos(data)")


def registrar_rotas_energia(app, conectar):
    @app.get("/perfil/medidas", response_model=list[MedidaEntrada], tags=["Evolução"])
    def listar_medidas():
        with closing(conectar()) as conn:
            return [dict(r) for r in conn.execute("SELECT data,peso_kg,cintura_cm FROM medidas_pessoais WHERE perfil_id=1 ORDER BY data")]

    @app.put("/perfil/medidas", response_model=MedidaEntrada, tags=["Evolução"])
    def salvar_medida(medida: MedidaEntrada):
        dados = medida.model_dump(mode="json")
        with closing(conectar()) as conn, conn:
            if not conn.execute("SELECT 1 FROM perfil_pessoal LIMIT 1").fetchone():
                raise HTTPException(409, "Cadastre seu perfil antes de registrar medidas")
            conn.execute("""INSERT INTO medidas_pessoais (perfil_id,data,peso_kg,cintura_cm)
                VALUES (1,:data,:peso_kg,:cintura_cm) ON CONFLICT(perfil_id,data)
                DO UPDATE SET peso_kg=excluded.peso_kg,cintura_cm=excluded.cintura_cm""", dados)
        return dados

    @app.put("/evolucao/refeicoes/{refeicao_id}", tags=["Evolução"])
    def visibilidade_refeicao(refeicao_id: int, visibilidade: VisibilidadeRefeicao):
        with closing(conectar()) as conn, conn:
            if not conn.execute("SELECT 1 FROM refeicoes WHERE id=?", (refeicao_id,)).fetchone():
                raise HTTPException(404, "Refeição não encontrada")
            if visibilidade.excluida:
                conn.execute("INSERT OR IGNORE INTO refeicoes_ocultas_evolucao VALUES (?)", (refeicao_id,))
            else:
                conn.execute("DELETE FROM refeicoes_ocultas_evolucao WHERE refeicao_id=?", (refeicao_id,))
        return dict(id=refeicao_id, excluida=visibilidade.excluida)

    @app.get("/evolucao", tags=["Evolução"])
    def evolucao():
        with closing(conectar()) as conn:
            perfis = [dict(r) for r in conn.execute("SELECT * FROM perfil_pessoal ORDER BY vigente_desde")]
            refeicoes = [dict(r) for r in conn.execute("""SELECT r.id,r.nome,r.data,r.horario,r.calorias,
                CASE WHEN o.refeicao_id IS NULL THEN 0 ELSE 1 END AS excluida
                FROM refeicoes r LEFT JOIN refeicoes_ocultas_evolucao o ON o.refeicao_id=r.id
                ORDER BY r.data DESC,r.horario,r.id""")]
            consumo = {r['data']: r['calorias'] for r in conn.execute("""SELECT data,ROUND(SUM(calorias),2) AS calorias
                FROM refeicoes WHERE id NOT IN (SELECT refeicao_id FROM refeicoes_ocultas_evolucao) GROUP BY data""")}
            treinos = {r['data']: r['calorias'] for r in conn.execute("SELECT data,ROUND(SUM(calorias),2) AS calorias FROM treinos GROUP BY data")}
        dias = []
        for dia in sorted({r['data'] for r in refeicoes} | treinos.keys()):
            perfil = next((p for p in reversed(perfis) if p['vigente_desde'] <= dia), None)
            tmb = perfil['tmb'] if perfil else None
            gasto = round(tmb + treinos.get(dia, 0), 2) if tmb is not None else None
            saldo = round(consumo[dia] - gasto, 2) if dia in consumo and gasto is not None else None
            dias.append(dict(data=dia, consumidas=consumo.get(dia), tmb=tmb,
                             treinos=treinos.get(dia, 0), gasto_referencia=gasto, saldo=saldo))
        atual = next((p for p in reversed(perfis) if p['vigente_desde'] <= date.today().isoformat()), None)
        return dict(dias=dias, refeicoes=refeicoes, tmb_atual=atual['tmb'] if atual else None,
                    tmb_vigente_desde=atual['vigente_desde'] if atual else None)

    @app.get("/perfil", response_model=Perfil | None, tags=["Energia"])
    def obter_perfil():
        with closing(conectar()) as conn:
            row = conn.execute("SELECT * FROM perfil_pessoal ORDER BY vigente_desde DESC LIMIT 1").fetchone()
            return dict(row) if row else None

    @app.put("/perfil", response_model=Perfil, tags=["Energia"])
    def salvar_perfil(perfil: PerfilEntrada):
        dados = {**perfil.model_dump(mode="json"), "tmb": calcular_tmb(perfil)}
        with closing(conectar()) as conn, conn:
            conn.execute("""INSERT INTO perfil_pessoal
                (vigente_desde, idade, peso_kg, altura_cm, sexo_formula, tmb)
                VALUES (:vigente_desde, :idade, :peso_kg, :altura_cm, :sexo_formula, :tmb)
                ON CONFLICT(vigente_desde) DO UPDATE SET idade=excluded.idade,
                peso_kg=excluded.peso_kg, altura_cm=excluded.altura_cm,
                sexo_formula=excluded.sexo_formula, tmb=excluded.tmb""", dados)
        return dados

    @app.post("/treinos", response_model=Treino, status_code=201, tags=["Energia"])
    def adicionar_treino(treino: TreinoEntrada):
        dados = treino.model_dump(mode="json")
        with closing(conectar()) as conn, conn:
            cursor = conn.execute("INSERT INTO treinos (nome,data,calorias) VALUES (:nome,:data,:calorias)", dados)
            return {"id": cursor.lastrowid, **dados}

    @app.delete("/treinos/{treino_id}", status_code=204, tags=["Energia"])
    def excluir_treino(treino_id: int):
        with closing(conectar()) as conn, conn:
            if not conn.execute("DELETE FROM treinos WHERE id=?", (treino_id,)).rowcount:
                raise HTTPException(404, "Treino não encontrado")
        return Response(status_code=204)

    @app.get("/balanco-diario", response_model=Balanco, tags=["Energia"])
    def balanco(data: date):
        with closing(conectar()) as conn:
            row = conn.execute("SELECT * FROM perfil_pessoal WHERE vigente_desde<=? ORDER BY vigente_desde DESC LIMIT 1", (data.isoformat(),)).fetchone()
            perfil = dict(row) if row else None
            treinos = [dict(r) for r in conn.execute("SELECT * FROM treinos WHERE data=? ORDER BY id", (data.isoformat(),))]
            consumo = conn.execute("SELECT ROUND(COALESCE(SUM(calorias),0),2) FROM refeicoes WHERE data=?", (data.isoformat(),)).fetchone()[0]
        gasto = round(sum(t["calorias"] for t in treinos), 2)
        referencia = round(perfil["tmb"] + gasto, 2) if perfil else None
        return dict(data=data, perfil=perfil, consumidas=consumo, treinos=treinos,
                    calorias_treinos=gasto, referencia=referencia,
                    diferenca_tmb=round(consumo-perfil["tmb"], 2) if perfil else None,
                    diferenca_referencia=round(consumo-referencia, 2) if perfil else None)
