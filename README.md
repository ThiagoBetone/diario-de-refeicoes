# Diário de refeições — FastAPI

Versão 0.2 para uso local e individual: catálogo de alimentos, cadastro e exclusão de refeições,
listagem por data e soma diária de calorias, proteínas, carboidratos e gorduras.
Inclui uma página de demonstração e documentação interativa em `/docs`.
Os dados persistem no arquivo SQLite `refeicoes.db`, criado automaticamente.

## Executar no Windows (PowerShell)

Requer Python 3.10 ou superior. Testado com Python 3.14.

```powershell
cd C:\git\prj_004
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m uvicorn main:app --reload --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000 para usar a tela ou http://127.0.0.1:8000/docs
para testar as rotas. Na tela, cadastre um alimento com os nutrientes por 100 g. Escolha o dia e o tipo
de refeição, pesquise o alimento, informe o peso consumido e clique em
**Adicionar à refeição**. Repita para os demais alimentos e clique em **Salvar refeição**.
Use `Ctrl+C` no terminal para encerrar.

## Rotas

| Método | Rota | Função |
| --- | --- | --- |
| POST | `/refeicoes` | Cadastrar uma refeição (201) |
| GET | `/refeicoes?data=2026-09-16` | Listar refeições da data |
| DELETE | `/refeicoes/1` | Excluir uma refeição (204; 404 se inexistente) |
| GET | `/resumo-diario?data=2026-09-16` | Consultar os totais da data |

Exemplo de corpo para `POST /refeicoes`:

```json
{
  "nome": "Almoço",
  "data": "2026-09-16",
  "horario": "12:30",
  "calorias": 550,
  "proteinas": 35,
  "carboidratos": 65,
  "gorduras": 16
}
```

Exemplo pelo PowerShell:

```powershell
$refeicao = @{
  nome = 'Almoço'; data = '2026-09-16'; horario = '12:30'
  calorias = 550; proteinas = 35; carboidratos = 65; gorduras = 16
} | ConvertTo-Json
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/refeicoes' -Method Post -ContentType 'application/json; charset=utf-8' -Body ([System.Text.Encoding]::UTF8.GetBytes($refeicao))
Invoke-RestMethod -Uri 'http://127.0.0.1:8000/resumo-diario?data=2026-09-16'
```

Após apenas esse cadastro, o resumo retorna:

```json
{
  "data": "2026-09-16",
  "quantidade_refeicoes": 1,
  "calorias": 550.0,
  "proteinas": 35.0,
  "carboidratos": 65.0,
  "gorduras": 16.0
}
```

## Como os valores funcionam

- Informe o total da porção efetivamente consumida: kcal e gramas, não valores por 100 g.
- Calorias são informadas diretamente; não são estimadas automaticamente pelos macros.
- O resumo soma as refeições da data local informada, arredondando para duas casas decimais.
- Datas sem refeições retornam zero. Campos inválidos retornam HTTP 422.
- Os valores dos exemplos são fictícios. O catálogo começa vazio e é preenchido manualmente.
- Esta versão não tem autenticação ou separação de usuários; destina-se ao uso local.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Os testes usam bancos temporários e verificam somas, isolamento por dia,
exclusão, validação, persistência e disponibilidade da página/documentação.

Referência: [documentação oficial do FastAPI sobre lifespan](https://fastapi.tiangolo.com/advanced/events/).

Se a pasta temporária do Windows negar acesso, use uma pasta nova dentro do projeto:

```powershell
$pastaTeste = Join-Path (Get-Location) (".test-run-" + [guid]::NewGuid().ToString())
.\.venv\Scripts\python.exe -m pytest -q --basetemp=$pastaTeste -p no:cacheprovider
```


## Catálogo de alimentos e refeições por gramas (v0.2)

O catálogo é a tabela auxiliar `alimentos` no mesmo SQLite. A atualização adiciona
as estruturas automaticamente, sem apagar as refeições anteriores.

- `POST /alimentos`: cadastrar nutrientes por **100 g** (kcal e gramas).
- `GET /alimentos?busca=pao`: pesquisar por parte do nome, sem diferenciar maiúsculas ou acentos.
- `POST /refeicoes`: aceita a nova lista `itens`; calcula os totais no servidor.
- `GET /refeicoes?data=2026-09-16`: retorna também os alimentos e pesos consumidos.

Exemplo de alimento (valores fictícios):

```json
{"nome":"Pão de exemplo","calorias":250,"proteinas":10,"carboidratos":40,"gorduras":5}
```

Use o `id` retornado ao cadastrar a refeição:

```json
{
  "nome": "Café da manhã",
  "data": "2026-09-16",
  "horario": "08:00",
  "itens": [{"alimento_id": 1, "quantidade_gramas": 50}]
}
```

Fórmula: `nutriente consumido = nutriente por 100 g × quantidade em gramas / 100`.
Nesse exemplo, 50 g fornecem 125 kcal, 5 g de proteínas, 20 g de carboidratos e
2,5 g de gorduras. As calorias vêm do cadastro, não de uma estimativa pelos macros.
Os totais da refeição são arredondados para duas casas após somar os itens.
A tela exibe uma prévia; o servidor recalcula a partir do catálogo ao salvar.

Cada refeição armazena uma cópia dos nomes, pesos e nutrientes consumidos,
preservando o histórico caso o catálogo seja modificado posteriormente.
Os registros antigos continuam visíveis como “Registro manual anterior”.
A API ainda aceita o corpo antigo com totais manuais, mas não permite misturá-lo
com `itens`. A tela usa o novo fluxo por alimentos.

Informe pelo menos um item e peso maior que zero. Alimentos inexistentes retornam
404 sem salvar parte da refeição; valores inválidos retornam 422.
Diferencie marcas e modo de preparo no nome. Edição e exclusão do catálogo ainda
não estão disponíveis nesta versão.

## Importação da TBCA

Foram importados 25 alimentos/variações da [TBCA](https://www.tbca.net.br/base-dados/composicao_alimentos.php), com nutrientes por 100 g da parte comestível.
A seleção é um catálogo inicial de alimentos comuns, não uma prescrição nutricional.
Nomes e modos de preparo foram preservados. O campo carboidratos usa **Carboidrato total**; energia usa **kcal**, proteína e lipídios usam **g**.
Valores ausentes, `NA` ou `tr` (traços) não são convertidos silenciosamente para zero.
A maçã Fuji BRC0064C ficou pendente por informar lipídios como `tr`.

O importador mantém código TBCA, URL da ficha e horário da coleta em UTC, com índice único para evitar duplicatas. Registros manuais e refeições não são alterados.
Cada importação faz backup do SQLite em `backups/` antes de modificar o catálogo.
A API `/alimentos` expõe os metadados de origem; a tela mostra o link da ficha ao selecionar um alimento.

Arquivos de auditoria em `data/tbca/`:

- `alimentos.json`: 25 registros validados, valores originais e valores numéricos.
- `pendencias.json`: registros não importados e motivo.
- `ultima_importacao.json`: resultado da importação e caminho do backup.
- `BRC*.html`: fichas consultadas para conferência local.
- `candidatos.json`: resultados das buscas usadas na seleção.

```powershell
# Importa os dados já coletados, sem acessar a internet e sem duplicar códigos.
.\.venv\Scripts\python.exe import_tbca.py importar
# Consultas seletivas à fonte; a coleta não escreve no banco.
.\.venv\Scripts\python.exe import_tbca.py buscar
.\.venv\Scripts\python.exe import_tbca.py coletar
```

Fonte: Tabela Brasileira de Composição de Alimentos (TBCA), USP/FoRC.
O site informa licença CC BY-NC-ND 4.0, exige atribuição e não permite comercialização.
A origem está identificada também na interface. As cópias locais servem para auditoria do uso pessoal; não são uma exportação completa da base.

## Quantidade por unidades

Na tela, selecione **Gramas** ou **Unidades**. A opção por unidades aceita frações,
como `0,5`, e usa o peso comestível de cada unidade para calcular os nutrientes.
O peso aparece na tela e pode ser ajustado para a porção antes de adicioná-la.
O cadastro manual aceita `peso_unidade_gramas` opcional como padrão do alimento.
Alimentos sem padrão também aceitam unidades, desde que o peso seja informado.

Referências das fichas TBCA já coletadas: ovo inteiro cozido BRC0010J, unidade média
50 g; banana-prata BRC0011C, unidade média 40 g. Esses pesos são estimativas da parte
comestível, sem casca. A maçã Fuji continua pendente na importação por conter `tr`
em lipídios; uma maçã cadastrada manualmente também pode usar unidades.

Exemplo de item na API (use o ID do alimento cadastrado):

```json
{"alimento_id": 1, "quantidade_unidades": 2, "peso_unidade_gramas": 50}
```

Quando existe peso padrão no catálogo, `peso_unidade_gramas` pode ser omitido.
Envie exclusivamente `quantidade_gramas` ou `quantidade_unidades`.
O servidor faz a conversão e grava no histórico as unidades, o peso usado por
unidade e o total em gramas. Ajustar o peso de uma porção não altera o catálogo
nem as refeições anteriores. O limite por item continua em 10000 g.

## Interface Bootstrap

A interface usa Bootstrap 5.3.8, com CSS local em static/vendor/bootstrap.min.css, servido por /static. O tema inclui cartões, formulários, botões e tabela responsiva. Não exige conexão externa para carregar os estilos nem etapa de build. A lógica permanece em JavaScript puro; não há componentes que exijam o JavaScript do Bootstrap. Documentação: https://getbootstrap.com/docs/5.3/getting-started/introduction/
