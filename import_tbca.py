"""Coleta seletiva de dados públicos da TBCA para o catálogo local."""
import argparse
import html
import json
import re
import sqlite3
import time
from pathlib import Path
from datetime import datetime, timezone
from urllib.parse import urljoin
import httpx

ROOT = Path(__file__).resolve().parent
BASE = 'https://www.tbca.net.br/base-dados/'
CACHE = ROOT / 'data' / 'tbca'
TERMS = ['Arroz, integral', 'Arroz, polido', 'Feijão, carioca', 'Feijão, preto', 'Lentilha', 'Aveia, flocos', 'Pão, integral', 'Batata, doce', 'Frango, peito', 'Ovo, galinha', 'Tilápia', 'Leite, vaca, integral', 'Iogurte, natural', 'Banana, prata', 'Maçã, Fuji', 'Laranja, pera', 'Mamão, Formosa', 'Brócolis', 'Cenoura', 'Tomate', 'Alface', 'Azeite', 'Castanha-do-brasil', 'Abacate']

def clean(s):
    return ' '.join(html.unescape(re.sub('<[^>]+>', '', s)).split())

def rows(s):
    return [[clean(c) for c in re.findall(r'<t[dh]\b[^>]*>(.*?)</t[dh]>', r, re.S|re.I)] for r in re.findall(r'<tr\b[^>]*>(.*?)</tr>', s, re.S|re.I)]

def search():
    CACHE.mkdir(parents=True, exist_ok=True)
    results = {}
    with httpx.Client(timeout=45, follow_redirects=True, headers={'User-Agent':'MealDiary/0.3 (personal food catalog research)'}) as client:
        for term in TERMS:
            r=client.post(BASE+'composicao_alimentos.php',data={'guarda':'tomo1','produto':term,'cmb_grupo':'','cmb_tipo_alimento':''})
            r.raise_for_status()
            found=[]
            for row in re.findall(r'<tr\b[^>]*>(.*?)</tr>',r.text,re.S|re.I):
                cells=re.findall(r'<td\b[^>]*>(.*?)</td>',row,re.S|re.I)
                if len(cells)<2: continue
                link=re.search(r'href=[\'"]([^\'"]*int_composicao_alimentos[^\'"]*)',cells[0])
                if link:
                    found.append({'codigo':clean(cells[0]),'nome':clean(cells[1]),'url':urljoin(BASE,html.unescape(link[1]))})
            results[term]=found
            print(term, len(found), flush=True)
            time.sleep(.4)
    (CACHE/'candidatos.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')

SELECTED = "BRC0016A BRC0208A BRC0001T BRC0254T BRC0008T BRC0018T BRC0024A BRC0155A BRC0042B BRC0114F BRC0010J BRC0486E BRC0044G BRC0020G BRC0011C BRC0064C BRC0020C BRC0045C BRC0045B BRC0020B BRC0047B BRC0035B BRC0060B BRC0002D BRC0003U BRC0001C".split()
MAP = {('Energia','kcal'):'calorias', ('Proteína','g'):'proteinas', ('Carboidrato total','g'):'carboidratos', ('Lipídios','g'):'gorduras'}

def parse_detail(page, candidate):
    table = rows(page)
    if not any(any('Valor por 100g' in c for c in row) for row in table):
        raise ValueError('Coluna por 100g não encontrada')
    if candidate['codigo'] not in clean(page):
        raise ValueError('Código do alimento não confere')
    raw = {}
    for row in table:
        if len(row) >= 3 and (row[0],row[1]) in MAP:
            raw[MAP[row[0],row[1]]] = row[2]
    if len(raw) != 4:
        raise ValueError('Nutrientes obrigatórios ausentes')
    nutrients = {}
    for key,value in raw.items():
        if not re.fullmatch(r'[0-9]+(?:,[0-9]+)?', value):
            raise ValueError(f'Valor não numérico: {key}={value}; não substituído por zero')
        nutrients[key]=float(value.replace(',','.'))
    from main import AlimentoEntrada
    AlimentoEntrada(nome=candidate['nome'], **nutrients)
    return {**candidate, **nutrients, 'valores_originais':raw, 'base_gramas':100,
            'carboidratos_tipo':'Carboidrato total', 'fonte':'TBCA',
            'coletado_em':datetime.now(timezone.utc).isoformat()}

def collect():
    candidates=json.loads((CACHE/'candidatos.json').read_text(encoding='utf-8'))
    by_code={r['codigo']:r for rs in candidates.values() for r in rs}
    records=[]; errors=[]
    with httpx.Client(timeout=45, follow_redirects=True) as client:
        for code in SELECTED:
            candidate=by_code[code]
            r=client.get(candidate['url']);r.raise_for_status()
            (CACHE/(code+'.html')).write_text(r.text,encoding='utf-8')
            try:
                record=parse_detail(r.text,candidate)
                records.append(record)
                print(code, {k:record[k] for k in MAP.values()}, flush=True)
            except ValueError as e:
                errors.append({'codigo':code,'motivo':str(e)})
                print(code,str(e),flush=True)
            time.sleep(.4)
    (CACHE/'alimentos.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    (CACHE/'pendencias.json').write_text(json.dumps(errors,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Coletados:',len(records),'Pendências:',len(errors))


def importar(db_path=ROOT/'refeicoes.db'):
    from main import AlimentoEntrada, preparar_catalogo
    records=json.loads((CACHE/'alimentos.json').read_text(encoding='utf-8'))
    # Validação completa antes de escrever qualquer registro.
    for record in records:
        AlimentoEntrada(nome=record['nome'], **{k:record[k] for k in MAP.values()})
        if record['base_gramas'] != 100 or not record['url'].startswith(BASE):
            raise ValueError('Fonte ou unidade inesperada')
    backup=ROOT/'backups'/('refeicoes-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')+'.db')
    backup.parent.mkdir(exist_ok=True)
    inserted=0
    with sqlite3.connect(db_path) as conn:
        with sqlite3.connect(backup) as dest:
            conn.backup(dest)
        preparar_catalogo(conn)
        for r in records:
            cursor=conn.execute("""INSERT INTO alimentos
                (nome,calorias,proteinas,carboidratos,gorduras,fonte,codigo_fonte,url_fonte,coletado_em,carboidratos_tipo,peso_unidade_gramas)
                VALUES (?,?,?,?,?,?,?,?,?,?,?) ON CONFLICT(fonte,codigo_fonte) DO NOTHING""",
                (r['nome'],r['calorias'],r['proteinas'],r['carboidratos'],r['gorduras'],
                 'TBCA',r['codigo'],r['url'],r['coletado_em'],r['carboidratos_tipo'],
                 {'BRC0010J':50,'BRC0011C':40,'BRC0064C':130}.get(r['codigo'])))
            inserted+=cursor.rowcount
    report={'inseridos':inserted,'ja_existentes':len(records)-inserted,'backup':str(backup),
            'codigos':[r['codigo'] for r in records]}
    (CACHE/'ultima_importacao.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False))
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('acao',choices=['buscar','coletar','importar'])
    args=parser.parse_args()
    {'buscar':search,'coletar':collect,'importar':importar}[args.acao]()
