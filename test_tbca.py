import json
import sqlite3
from pathlib import Path
import pytest
from fastapi.testclient import TestClient
import import_tbca as tbca
from main import create_app


def test_extracao_100g_e_unidades():
    records=json.loads((tbca.CACHE/'alimentos.json').read_text(encoding='utf-8'))
    assert len(records)==25
    for record in records:
        page=(tbca.CACHE/(record['codigo']+'.html')).read_text(encoding='utf-8')
        parsed=tbca.parse_detail(page,record)
        for key in tbca.MAP.values():
            assert parsed[key]==record[key]
    arroz=next(r for r in records if r['codigo']=='BRC0016A')
    assert arroz['calorias']==108
    assert arroz['carboidratos']==23.5


def test_tracos_nao_sao_zero():
    candidates=json.loads((tbca.CACHE/'candidatos.json').read_text(encoding='utf-8'))
    maca=next(r for rs in candidates.values() for r in rs if r['codigo']=='BRC0064C')
    with pytest.raises(ValueError,match='não substituído por zero'):
        tbca.parse_detail((tbca.CACHE/'BRC0064C.html').read_text(encoding='utf-8'),maca)


def test_importacao_idempotente_e_calculo(tmp_path,monkeypatch):
    records=(tbca.CACHE/'alimentos.json').read_text(encoding='utf-8')
    monkeypatch.setattr(tbca,'ROOT',tmp_path)
    monkeypatch.setattr(tbca,'CACHE',tmp_path)
    (tmp_path/'alimentos.json').write_text(records,encoding='utf-8')
    banco=tmp_path/'test.db'
    with TestClient(create_app(banco)) as client:
        manual=client.post('/alimentos',json=dict(nome='Manual',calorias=100,proteinas=1,carboidratos=2,gorduras=3)).json()
        assert tbca.importar(banco)['inseridos']==25
        assert tbca.importar(banco)['inseridos']==0
        alimentos=client.get('/alimentos').json()
        assert len(alimentos)==26
        assert next(a for a in alimentos if a['id']==manual['id'])==manual
        arroz=next(a for a in alimentos if a['codigo_fonte']=='BRC0016A')
        assert arroz['fonte']=='TBCA'
        r=client.post('/refeicoes',json=dict(nome='Teste',data='2026-09-16',itens=[dict(alimento_id=arroz['id'],quantidade_gramas=50)]))
        assert r.status_code==201
        assert r.json()['calorias']==54
        assert r.json()['carboidratos']==11.75
