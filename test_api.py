import pytest
from fastapi.testclient import TestClient
from main import create_app


def refeicao(**alteracoes):
    return dict(nome="Almoço", data="2026-09-16", horario="12:30",
                calorias=550, proteinas=35, carboidratos=65, gorduras=16) | alteracoes


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / "teste.db")) as client:
        yield client


def test_soma_filtra_data_e_exclui(client):
    primeira = client.post("/refeicoes", json=refeicao())
    assert primeira.status_code == 201
    client.post("/refeicoes", json=refeicao(nome="Jantar", calorias=300.25, proteinas=20.5,
                                         carboidratos=30, gorduras=10))
    client.post("/refeicoes", json=refeicao(data="2026-09-17"))
    assert len(client.get("/refeicoes?data=2026-09-16").json()) == 2
    assert client.get("/resumo-diario?data=2026-09-16").json() == dict(
        data="2026-09-16", quantidade_refeicoes=2, calorias=850.25,
        proteinas=55.5, carboidratos=95, gorduras=26)
    url = f"/refeicoes/{primeira.json()['id']}"
    assert client.delete(url).status_code == 204
    assert client.delete(url).status_code == 404
    assert client.get("/resumo-diario?data=2026-09-16").json()["calorias"] == 300.25


def test_dia_vazio(client):
    assert client.get("/resumo-diario?data=2026-09-15").json() == dict(
        data="2026-09-15", quantidade_refeicoes=0, calorias=0,
        proteinas=0, carboidratos=0, gorduras=0)


@pytest.mark.parametrize("alteracoes", [dict(nome="  "), dict(calorias=-1),
    dict(proteinas=-1), dict(carboidratos=-1), dict(gorduras=-1),
    dict(data="2026-02-30"), dict(horario="25:00"), dict(calorias="NaN"),
    dict(proteinas="Infinity")])
def test_dados_invalidos(client, alteracoes):
    assert client.post("/refeicoes", json=refeicao(**alteracoes)).status_code == 422


def test_persistencia(tmp_path):
    banco = tmp_path / "persistencia.db"
    with TestClient(create_app(banco)) as client:
        client.post("/refeicoes", json=refeicao())
    with TestClient(create_app(banco)) as client:
        assert len(client.get("/refeicoes?data=2026-09-16").json()) == 1


def test_pagina_e_documentacao(client):
    assert client.get("/").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").status_code == 200


def alimento(client, **alteracoes):
    resposta = client.post('/alimentos', json=dict(nome='Pão de teste', calorias=250,
        proteinas=10, carboidratos=40, gorduras=5) | alteracoes)
    assert resposta.status_code == 201
    return resposta.json()


def test_alimentos_calculo_e_busca(client):
    pao = alimento(client)
    leite = alimento(client, nome='Leite de teste', calorias=60, proteinas=3,
                     carboidratos=5, gorduras=3)
    assert client.get('/alimentos?busca=PAO').json() == [pao]
    assert client.get('/alimentos?busca=%25').json() == []
    dados = dict(nome='Café da manhã', data='2026-09-16', horario='08:00', itens=[
        dict(alimento_id=pao['id'], quantidade_gramas=50),
        dict(alimento_id=leite['id'], quantidade_gramas=200)])
    resposta = client.post('/refeicoes', json=dados)
    assert resposta.status_code == 201, resposta.text
    refeicao = resposta.json()
    assert refeicao['calorias'] == 245
    assert refeicao['proteinas'] == 11
    assert refeicao['carboidratos'] == 30
    assert refeicao['gorduras'] == 8.5
    assert refeicao['itens'][0]['nome'] == pao['nome']
    assert refeicao['itens'][0]['calorias'] == 125
    assert client.get('/refeicoes?data=2026-09-16').json() == [refeicao]
    assert client.get('/resumo-diario?data=2026-09-16').json()['calorias'] == 245


@pytest.mark.parametrize('quantidade', [0, -1, 'NaN', 'Infinity', 10001])
def test_quantidade_invalida(client, quantidade):
    item = alimento(client)
    assert client.post('/refeicoes', json=dict(nome='Café', data='2026-09-16',
        itens=[dict(alimento_id=item['id'], quantidade_gramas=quantidade)])).status_code == 422


def test_itens_vazios_e_alimento_inexistente(client):
    dados = dict(nome='Café', data='2026-09-16', itens=[])
    assert client.post('/refeicoes', json=dados).status_code == 422
    item = alimento(client)
    dados['itens'] = [dict(alimento_id=item['id'], quantidade_gramas=50),
                     dict(alimento_id=9999, quantidade_gramas=100)]
    assert client.post('/refeicoes', json=dados).status_code == 404
    assert client.get('/refeicoes?data=2026-09-16').json() == []


@pytest.mark.parametrize('alteracoes', [dict(nome=' '), dict(calorias=-1),
    dict(proteinas=101), dict(gorduras=-1), dict(carboidratos='NaN')])
def test_alimento_invalido(client, alteracoes):
    dados = dict(nome='Teste', calorias=100, proteinas=1, carboidratos=2, gorduras=3)
    assert client.post('/alimentos', json=dados | alteracoes).status_code == 422


def test_migracao_e_snapshot(tmp_path):
    import sqlite3
    banco = tmp_path / 'antigo.db'
    with sqlite3.connect(banco) as conn:
        conn.execute('CREATE TABLE refeicoes (id INTEGER PRIMARY KEY, nome TEXT, data TEXT, horario TEXT, calorias REAL, proteinas REAL, carboidratos REAL, gorduras REAL)')
        conn.execute("INSERT INTO refeicoes VALUES (1, 'Antiga', '2026-09-16', '12:00', 100, 10, 10, 2)")
    with TestClient(create_app(banco)) as c:
        assert c.get('/refeicoes?data=2026-09-16').json()[0]['itens'] == []
        item = alimento(c)
        r = c.post('/refeicoes', json=dict(nome='Café', data='2026-09-17', itens=[
            dict(alimento_id=item['id'], quantidade_gramas=33.33)]))
        assert r.status_code == 201
        assert r.json()['calorias'] == 83.33
    with sqlite3.connect(banco) as conn:
        conn.execute('UPDATE alimentos SET calorias=999, nome=?', ('Alterado',))
    with TestClient(create_app(banco)) as c:
        historico = c.get('/refeicoes?data=2026-09-17').json()[0]
        assert historico['calorias'] == 83.33
        assert historico['itens'][0]['nome'] == item['nome']
        assert len(c.get('/alimentos').json()) == 1


def test_unidades_e_peso_personalizado(client):
    ovo=alimento(client,nome='Ovo',calorias=125,proteinas=10.4,carboidratos=1.38,gorduras=8.7,peso_unidade_gramas=50)
    dados=dict(nome='Café',data='2026-09-16',itens=[dict(alimento_id=ovo['id'],quantidade_unidades=2)])
    r=client.post('/refeicoes',json=dados)
    assert r.status_code==201, r.text
    assert r.json()['calorias']==125
    item=r.json()['itens'][0]
    assert item['quantidade_gramas']==100
    assert item['quantidade_unidades']==2
    assert item['peso_unidade_gramas']==50
    assert client.get('/refeicoes?data=2026-09-16').json()[0]==r.json()
    dados['itens'][0].update(quantidade_unidades=0.5,peso_unidade_gramas=60)
    r=client.post('/refeicoes',json=dados)
    assert r.status_code==201
    assert r.json()['itens'][0]['quantidade_gramas']==30
    assert r.json()['calorias']==37.5
    assert client.get('/alimentos?busca=Ovo').json()[0]['peso_unidade_gramas']==50
    assert client.get('/resumo-diario?data=2026-09-16').json()['calorias']==162.5


@pytest.mark.parametrize('campos', [dict(),dict(quantidade_unidades=0),dict(quantidade_unidades=-1),
    dict(quantidade_unidades='NaN'),dict(quantidade_unidades=2,quantidade_gramas=50),
    dict(quantidade_gramas=50,peso_unidade_gramas=10),
    dict(quantidade_unidades=2,peso_unidade_gramas=0),
    dict(quantidade_unidades=2,peso_unidade_gramas=6000)])
def test_unidades_invalidas(client,campos):
    a=alimento(client,peso_unidade_gramas=50)
    r=client.post('/refeicoes',json=dict(nome='Café',data='2026-09-16',itens=[dict(alimento_id=a['id'],**campos)]))
    assert r.status_code==422
    assert client.get('/refeicoes?data=2026-09-16').json()==[]


def test_unidade_sem_peso_exige_conversao(client):
    a=alimento(client)
    dados=dict(nome='Café',data='2026-09-16',itens=[dict(alimento_id=a['id'],quantidade_unidades=1)])
    assert client.post('/refeicoes',json=dados).status_code==422
    dados['itens'][0]['peso_unidade_gramas']=130
    r=client.post('/refeicoes',json=dados)
    assert r.status_code==201
    assert r.json()['itens'][0]['quantidade_gramas']==130


def test_migracao_pesos_tbca(tmp_path):
    import sqlite3
    banco=tmp_path/'pesos.db'
    with sqlite3.connect(banco) as conn:
        conn.execute('CREATE TABLE alimentos (id INTEGER PRIMARY KEY, nome TEXT, calorias REAL, proteinas REAL, carboidratos REAL, gorduras REAL, fonte TEXT, codigo_fonte TEXT)')
        for i,code in enumerate(['BRC0010J','BRC0011C','BRC0064C']):
            conn.execute('INSERT INTO alimentos VALUES (?, ?, 100, 1, 1, 1, ?, ?)',(i+1,code,'TBCA',code))
    with TestClient(create_app(banco)) as c:
        assert {a['codigo_fonte']:a['peso_unidade_gramas'] for a in c.get('/alimentos').json()}=={'BRC0010J':50,'BRC0011C':40,'BRC0064C':130}
    with sqlite3.connect(banco) as conn:
        conn.execute('UPDATE alimentos SET peso_unidade_gramas=55 WHERE codigo_fonte=?',('BRC0010J',))
    with TestClient(create_app(banco)) as c:
        assert c.get('/alimentos?busca=BRC0010J').json()[0]['peso_unidade_gramas']==55
