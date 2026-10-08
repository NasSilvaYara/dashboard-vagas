import html
import requests
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import timedelta

st.set_page_config(page_title="Dashboard de Vagas", layout="wide", initial_sidebar_state="collapsed")

st.markdown(
    """
    <style>
        html, body, .stApp,
        [data-testid="stAppViewContainer"],
        [data-testid="stMain"],
        [data-testid="stMainBlockContainer"],
        .main { background: #191919 !important; }
        header, footer, #MainMenu,
        [data-testid="stToolbar"],
        [data-testid="stDecoration"],
        [data-testid="stStatusWidget"],
        [data-testid="stHeader"] { display: none !important; }
        .block-container { padding: 0 !important; max-width: 100% !important; }
        iframe { border: none !important; background: #191919 !important; }
    </style>
    """,
    unsafe_allow_html=True,
)

try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
    DATABASE_ID = st.secrets["DATABASE_ID"]
except Exception:
    st.error("Configure NOTION_TOKEN e DATABASE_ID nos Secrets do Streamlit.")
    st.stop()

HEADERS = {
    "Authorization": f"Bearer {NOTION_TOKEN}",
    "Notion-Version": "2022-06-28",
    "Content-Type": "application/json",
}


def juntar(lista):
    return "".join(x.get("plain_text", "") for x in lista)


@st.cache_data(ttl=600)
def titulo_pagina(page_id):
    r = requests.get(f"https://api.notion.com/v1/pages/{page_id}", headers=HEADERS)
    if r.status_code != 200:
        return ""
    for prop in r.json().get("properties", {}).values():
        if prop.get("type") == "title":
            return juntar(prop.get("title", []))
    return ""


def extrair(t, v):
    if v is None:
        return ""
    if t in ("title", "rich_text"):
        return juntar(v)
    if t in ("select", "status"):
        return v.get("name", "")
    if t == "multi_select":
        return ", ".join(x.get("name", "") for x in v)
    if t == "date":
        return v.get("start", "") or ""
    if t == "checkbox":
        return "Sim" if v else "Não"
    if t in ("url", "email", "phone_number", "string", "created_time", "last_edited_time"):
        return str(v)
    if t in ("number", "boolean"):
        return str(v)
    if t == "people":
        return ", ".join(x.get("name", "") for x in v)
    if t == "relation":
        return ", ".join(titulo_pagina(x["id"]) for x in v)
    if t == "formula":
        ft = v.get("type")
        return extrair(ft, v.get(ft))
    if t == "rollup":
        rt = v.get("type")
        if rt == "array":
            partes = []
            for item in v.get("array", []):
                it = item.get("type")
                partes.append(extrair(it, item.get(it)))
            return ", ".join(p for p in partes if p)
        return extrair(rt, v.get(rt))
    return ""


@st.cache_data(ttl=30)
def carregar():
    url = f"https://api.notion.com/v1/databases/{DATABASE_ID}/query"
    registros = []
    tipos = {}
    cursor = None
    while True:
        payload = {"start_cursor": cursor} if cursor else {}
        r = requests.post(url, json=payload, headers=HEADERS)
        if r.status_code != 200:
            raise Exception(f"Erro na API do Notion ({r.status_code}): {r.text}")
        dados = r.json()
        for page in dados.get("results", []):
            linha = {}
            for nome, prop in page.get("properties", {}).items():
                t = prop.get("type")
                tipos[nome] = t
                linha[nome] = extrair(t, prop.get(t))
            registros.append(linha)
        if not dados.get("has_more"):
            break
        cursor = dados.get("next_cursor")
    return pd.DataFrame(registros), tipos


try:
    df, tipos = carregar()
except Exception as e:
    st.error(str(e))
    st.stop()

if df.empty:
    st.warning("A base retornou vazia.")
    st.stop()

df.columns = [c.strip() for c in df.columns]
tipos = {k.strip(): v for k, v in tipos.items()}


def achar(opcoes, padrao=None):
    for c in df.columns:
        if c.lower() in opcoes:
            return c
    return padrao


col_cod = achar(["cod", "código", "codigo"])
col_prazo = achar(["prazo final", "prazofinal", "prazo"])
col_curso = achar(["curso", "vaga"])
col_status = achar(["status"])
col_link = achar(["link da vaga", "link"])
col_titulo = next((c for c, t in tipos.items() if t == "title" and c in df.columns), None)

if col_prazo:
    df[col_prazo] = pd.to_datetime(df[col_prazo], errors="coerce", utc=True).dt.tz_localize(None)


def nome_vaga(idx, row):
    for c in (col_curso, col_titulo):
        if c and c in df.columns:
            v = str(row.get(c, "")).strip()
            if v and v.lower() != "nan":
                return html.escape(v)
    return f"Linha {idx}"


total = len(df)
postadas = 0
if col_status:
    s = df[col_status].astype(str).str.strip().str.lower()
    marcado = s.str.contains("postad", na=False) & ~s.str.contains(r"n[ãa]o", na=False)
    postadas = int((marcado | (s == "sim")).sum())
pendentes = total - postadas

alerta = ""
grupos_n = 0
if col_cod:
    cods = df[col_cod].astype(str).str.strip()
    mask = cods.duplicated(keep=False) & (cods != "") & (cods.str.lower() != "nan")
    dup = df[mask]
    itens = ""
    if not dup.empty:
        for cod, grupo in dup.groupby(cods[mask]):
            grupos_n += 1
            vagas = " &bull; ".join(
                f"<b>{nome_vaga(i, r)}</b> (Linha {i})" for i, r in grupo.iterrows()
            )
            itens += f"""
            <li style="margin-bottom:8px;">Código <b style="color:#FF6B6B;">"{html.escape(cod)}"</b> ({len(grupo)}x) — Vagas envolvidas:
            <div style="margin-top:2px;color:#B8B8B8;font-size:12px;padding-left:10px;">{vagas}</div></li>"""
        alerta = f"""
        <div style="background:#2A1D1D;border:1px solid #5C2B2B;border-radius:8px;padding:16px 20px;color:#E6E6E6;margin-bottom:24px;">
            <div style="color:#FF6B6B;font-weight:bold;font-size:15px;">⚠️ ATENÇÃO: Códigos Repetidos Encontrados na coluna Cod ({grupos_n} código(s) em conflito)</div>
            <ul style="margin:12px 0 0 20px;padding:0;font-size:13px;">{itens}</ul>
        </div>"""

hoje = pd.Timestamp.now(tz="America/Sao_Paulo").tz_localize(None).normalize()
dias_limite = 30
linhas = ""
n_urgentes = 0
if col_prazo:
    urg = df[
        df[col_prazo].notna()
        & (df[col_prazo] >= hoje)
        & (df[col_prazo] <= hoje + timedelta(days=dias_limite))
    ].sort_values(col_prazo)
    n_urgentes = len(urg)
    for idx, row in urg.iterrows():
        link = ""
        for c in (col_link, col_cod):
            if c:
                v = str(row.get(c, "")).strip()
                if v and v.lower() != "nan":
                    link = v
                    break
        if link:
            destino = link if link.startswith(("http://", "https://")) else f"https://{link}"
            botao = f'<a href="{html.escape(destino)}" target="_blank" style="background:#2383E2;color:#FFF;padding:6px 14px;border-radius:6px;text-decoration:none;font-size:12px;font-weight:600;">Acessar Página ↗</a>'
        else:
            botao = '<span style="color:#777;font-size:12px;">Sem link</span>'
        linhas += f"""
        <tr>
            <td style="padding:14px;border-bottom:1px solid #2F2F2F;"><b>{nome_vaga(idx, row)}</b></td>
            <td style="padding:14px;border-bottom:1px solid #2F2F2F;color:#FF6B6B;font-weight:bold;">{row[col_prazo].strftime('%d/%m/%Y')}</td>
            <td style="padding:14px;border-bottom:1px solid #2F2F2F;text-align:center;">{botao}</td>
        </tr>"""
if not linhas:
    linhas = f'<tr><td colspan="3" style="padding:20px;text-align:center;color:#9B9B9B;">Nenhuma vaga prestes a vencer nos próximos {dias_limite} dias! 🎉</td></tr>'

pagina = f"""
<style>
    html, body {{ margin:0; padding:0; background:#191919; }}
    body {{ font-family:'Segoe UI',sans-serif; color:#E6E6E6; overflow:hidden; }}
    .dash {{ padding:20px; background:#191919; }}
    .grid {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:16px; }}
    .card {{ background:#202020; border:1px solid #2F2F2F; padding:20px; border-radius:8px; }}
    .label {{ font-size:12px; text-transform:uppercase; letter-spacing:.8px; color:#9B9B9B; font-weight:600; }}
    .valor {{ font-size:32px; font-weight:800; margin-top:8px; color:#FFF; }}
    table {{ width:100%; border-collapse:collapse; margin-top:16px; }}
    th {{ text-align:left; padding:12px 14px; background:#202020; color:#9B9B9B; font-size:12px; text-transform:uppercase; }}
</style>
<div class="dash">
    {alerta}
    <div class="grid">
        <div class="card" style="border-left:4px solid #2383E2;"><div class="label">Total de Vagas</div><div class="valor">{total}</div></div>
        <div class="card" style="border-left:4px solid #2ECC71;"><div class="label">Postadas</div><div class="valor" style="color:#2ECC71;">{postadas}</div></div>
        <div class="card" style="border-left:4px solid #FF6B6B;"><div class="label">Pendentes</div><div class="valor" style="color:#FF6B6B;">{pendentes}</div></div>
    </div>
    <div style="margin-top:24px;">
        <h3 style="margin:0;color:#FFF;">🚨 Vagas Perto de Vencer (Próximos {dias_limite} dias)</h3>
        <table>
            <thead><tr><th>Curso / Vaga</th><th>Data Limite</th><th style="text-align:center;">Link da Página</th></tr></thead>
            <tbody>{linhas}</tbody>
        </table>
    </div>
</div>
"""

altura = 300 + 72 * max(n_urgentes, 1) + (130 + 100 * grupos_n if alerta else 0)
components.html(pagina, height=altura, scrolling=False)
