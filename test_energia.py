import pytest
from fastapi.testclient import TestClient
from main import create_app


@pytest.fixture
def client(tmp_path):
    with TestClient(create_app(tmp_path / 'energia.db')) as c:
        yield c


def perfil(**kwargs):
    return dict(idade=30, peso_kg=80, altura_cm=180, sexo_formula='masculino', vigente_desde='2026-09-16') | kwargs


@pytest.mark.parametrize('sexo,tmb', [('masculino', 1780), ('feminino', 1614)])
def test_formula(client, sexo, tmb):
    r = client.put('/perfil', json=perfil(sexo_formula=sexo))
    assert r.status_code == 200
    assert r.json()['tmb'] == tmb
    assert client.get('/perfil').json() == r.json()


def test_balanco_datas_e_exclusao(client):
    assert client.get('/perfil').json() is None
    inicial = client.get('/balanco-diario?data=2026-09-16').json()
    assert inicial['referencia'] is None
    assert inicial['consumidas'] == 0
    client.put('/perfil', json=perfil())
    client.post('/refeicoes', json=dict(nome='Almoço', data='2026-09-16', calorias=2000, proteinas=10, carboidratos=20, gorduras=5))
    treino = client.post('/treinos', json=dict(nome='Corrida', data='2026-09-16', calorias=300)).json()
    client.post('/treinos', json=dict(nome='Bike', data='2026-09-16', calorias=150.5))
    client.post('/treinos', json=dict(nome='Outro dia', data='2026-09-17', calorias=900))
    b = client.get('/balanco-diario?data=2026-09-16').json()
    assert b['calorias_treinos'] == 450.5
    assert b['referencia'] == 2230.5
    assert b['diferenca_tmb'] == 220
    assert b['diferenca_referencia'] == -230.5
    assert len(b['treinos']) == 2
    assert client.delete(f"/treinos/{treino['id']}").status_code == 204
    assert client.delete(f"/treinos/{treino['id']}").status_code == 404
    assert client.get('/balanco-diario?data=2026-09-16').json()['referencia'] == 1930.5
    assert client.get('/balanco-diario?data=2026-09-15').json()['perfil'] is None


def test_historico_e_correcao(client):
    client.put('/perfil', json=perfil())
    client.put('/perfil', json=perfil(peso_kg=75, vigente_desde='2026-09-18'))
    assert client.get('/balanco-diario?data=2026-09-17').json()['perfil']['tmb'] == 1780
    assert client.get('/balanco-diario?data=2026-09-18').json()['perfil']['tmb'] == 1730
    client.put('/perfil', json=perfil(peso_kg=76, vigente_desde='2026-09-18'))
    assert client.get('/balanco-diario?data=2026-09-18').json()['perfil']['tmb'] == 1740


@pytest.mark.parametrize('dados', [dict(idade=17), dict(idade=30.5), dict(peso_kg='NaN'), dict(altura_cm=0), dict(sexo_formula='x'), dict(vigente_desde='2026-02-30'), dict(peso_kg=-1)])
def test_perfil_invalido(client, dados):
    assert client.put('/perfil', json=perfil(**dados)).status_code == 422
    assert client.get('/perfil').json() is None


@pytest.mark.parametrize('dados', [dict(nome=' '), dict(calorias=-1), dict(calorias=0), dict(calorias='Infinity'), dict(data='inválida')])
def test_treino_invalido(client, dados):
    assert client.post('/treinos', json=dict(nome='Treino',data='2026-09-16',calorias=100) | dados).status_code == 422


def test_persistencia(tmp_path):
    banco = tmp_path/'persistencia.db'
    with TestClient(create_app(banco)) as c:
        c.put('/perfil', json=perfil())
        c.post('/treinos', json=dict(nome='Treino',data='2026-09-16',calorias=100))
    with TestClient(create_app(banco)) as c:
        b = c.get('/balanco-diario?data=2026-09-16').json()
        assert b['referencia'] == 1880
        assert len(b['treinos']) == 1
