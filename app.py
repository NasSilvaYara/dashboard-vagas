import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from notion_client import Client

# Configuração da página (Layout largo)
st.set_page_config(page_title="Dashboard de Vagas", layout="wide")

# Puxa as chaves de segurança configuradas no Streamlit Secrets
try:
    NOTION_TOKEN = st.secrets["NOTION_TOKEN"]
    DATABASE_ID = st.secrets["DATABASE_ID"]
except Exception:
    st.error(" As credenciais (Secrets) do Notion não foram encontradas nas configurações do Streamlit.")
    st.stop()

# Função que conecta no Notion e traz os dados reais da sua base
@st.cache_data(ttl=30)
def carregar_dados_notion():
    notion = Client(auth=NOTION_TOKEN)
    registros = []
    has_more = True
    start_cursor = None
    
    while has_more:
        response = notion.databases.query(database_id=DATABASE_ID, start_cursor=start_cursor)
        for page in response.get("results", []):
            props = page.get("properties", {})
            linha = {}
            for nome_col, dados in props.items():
                tipo = dados.get("type")
                if tipo == "title":
                    vals = dados.get("title", [])
                    linha[nome_col] = vals[0]["plain_text"] if vals else ""
                elif tipo == "rich_text":
                    vals = dados.get("rich_text", [])
                    linha[nome_col] = vals[0]["plain_text"] if vals else ""
                elif tipo == "select":
                    select = dados.get("select")
                    linha[nome_col] = select["name"] if select else ""
                elif tipo == "date":
                    date = dados.get("date")
                    linha[nome_col] = date["start"] if date else ""
                elif tipo == "url":
                    linha[nome_col] = dados.get("url", "")
            registros.append(linha)
            
        has_more = response.get("has_more", False)
        start_cursor = response.get("next_cursor")
        
    return pd.DataFrame(registros)

# Carrega os dados
with st.spinner("Conectando ao Notion e carregando as vagas..."):
    try:
        df_dash = carregar_dados_notion()
    except Exception as e:
        st.error(f"Erro ao conectar com o Notion: {e}")
        st.stop()

if df_dash.empty:
    st.warning("A base de dados do Notion retornou vazia ou a integração não tem permissão de leitura na página.")
    st.stop()

# Mapeamento de colunas
col_cod = next((col for col in df_dash.columns if col.upper() == 'COD'), 'COD')
col_prazo = next((col for col in df_dash.columns if col.lower() in ['prazo final', 'prazofinal', 'prazo']), 'Prazo final')
col_curso = next((col for col in df_dash.columns if col.lower() in ['curso', 'vaga']), 'Curso')
col_status = next((col for col in df_dash.columns if col.lower() in ['status']), 'Status')

if col_prazo in df_dash.columns:
    df_dash[col_prazo] = pd.to_datetime(df_dash[col_prazo], errors='coerce')

total_vagas = len(df_dash)
postadas = len(df_dash[df_dash[col_status] == 'Postado']) if col_status in df_dash.columns else 0
pendentes = len(df_dash[df_dash[col_status] == 'Não postado']) if col_status in df_dash.columns else 0

# --- LÓGICA DE DUPLICADOS ---
html_alerta_duplicados = ""
if col_cod in df_dash.columns:
    cods_limpos = df_dash[col_cod].astype(str).str.strip()
    mascara_duplicados = cods_limpos.duplicated(keep=False) & (cods_limpos != '') & (cods_limpos != 'nan') & df_dash[col_cod].notna()
    df_duplicados = df_dash[mascara_duplicados].copy()
    
    if not df_duplicados.empty:
        grupos = df_duplicados.groupby(cods_limpos[mascara_duplicados])
        itens_duplicados_html = ""
        for cod, group in grupos:
            vagas_info = []
            for idx, row in group.iterrows():
                nome_curso = row.get(col_curso, f"Linha {idx}")
                vagas_info.append(f"<b>{nome_curso}</b> (Linha {idx})")
            
            detalhe_vagas = " &bull; ".join(vagas_info)
            itens_duplicados_html += f"""
            <li style="margin-bottom: 8px;">
                Código <b style="color: #FF5252;">"{cod}"</b> ({len(group)}x) — Vagas envolvidas:
                <div style="margin-top: 2px; color: #D0D0DE; font-size: 12px; padding-left: 10px;">
                    {detalhe_vagas}
                </div>
            </li>
            """
        
        html_alerta_duplicados = f"""
        <div style="background-color: #2E1B22; border: 1px solid #FF5252; border-radius: 12px; padding: 16px 20px; color: #E8E8EE; margin-bottom: 24px; font-family: 'Segoe UI', sans-serif;">
            <div style="display: flex; align-items: center; gap: 8px; color: #FF5252; font-weight: bold; font-size: 15px;">
                <span> ATENÇÃO: Códigos Repetidos Encontrados na coluna COD ({len(grupos)} código(s) em conflito)</span>
            </div>
            <ul style="margin: 12px 0 0 20px; padding: 0; color: #E8E8EE; font-size: 13px;">
                {itens_duplicados_html}
            </ul>
        </div>
        """

# --- HTML DOS 3 CARDS ---
html_kpis = f"""
<style>
    .dash-container {{
        font-family: 'Segoe UI', sans-serif;
        background-color: #17161F;
        padding: 24px;
        border-radius: 16px;
        color: #E8E8EE;
        margin-bottom: 24px;
    }}
    .kpi-grid {{
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
        gap: 16px;
    }}
    .kpi-card {{
        background: #22202E;
        border: 1px solid #2D2C3A;
        padding: 20px;
        border-radius: 12px;
    }}
    .kpi-label {{
        font-size: 12px;
        text-transform: uppercase;
        letter-spacing: 0.8px;
        color: #9E9EAE;
        font-weight: 600;
    }}
    .kpi-value {{
        font-size: 32px;
        font-weight: 800;
        margin-top: 8px;
        color: #FFFFFF;
    }}
</style>

{html_alerta_duplicados}

<div class="dash-container">
    <div class="kpi-grid">
        <div class="kpi-card" style="border-left: 4px solid #3A28FF;">
            <div class="kpi-label">Total de Vagas</div>
            <div class="kpi-value">{total_vagas}</div>
        </div>
        <div class="kpi-card" style="border-left: 4px solid #2ECC71;">
            <div class="kpi-label">Postadas</div>
            <div class="kpi-value" style="color: #2ECC71;">{postadas}</div>
        </div>
        <div class="kpi-card" style="border-left: 4px solid #FF5252;">
            <div class="kpi-label">Pendentes</div>
            <div class="kpi-value" style="color: #FF5252;">{pendentes}</div>
        </div>
    </div>
</div>
"""

st.markdown(html_kpis, unsafe_allow_html=True)

# --- QUADRO DE URGÊNCIA ---
hoje = pd.Timestamp.now().normalize()
dias_limite = 30

if col_prazo in df_dash.columns:
    df_urgentes = df_dash[
        (df_dash[col_prazo].notna()) & 
        (df_dash[col_prazo] >= hoje) & 
        (df_dash[col_prazo] <= hoje + timedelta(days=dias_limite))
    ].sort_values(col_prazo).copy()

    linhas_tabela = ""
    if len(df_urgentes) > 0:
        for _, row in df_urgentes.iterrows():
            curso_vaga = row.get(col_curso, 'Não informado')
            prazo = row[col_prazo].strftime('%d/%m/%Y')
            link_url = row.get(col_cod, '#')

            if pd.notna(link_url) and str(link_url).strip() != '' and link_url != '#':
                val_link = str(link_url).strip()
                url_destino = val_link if val_link.startswith(('http://', 'https://')) else f"https://{val_link}"
                btn_link = f'<a href="{url_destino}" target="_blank" style="background:#3A28FF; color:#FFF; padding:6px 14px; border-radius:6px; text-decoration:none; font-size:12px; font-weight:600;">Acessar Página ↗</a>'
            else:
                btn_link = '<span style="color:#777; font-size:12px;">Sem link</span>'

            linhas_tabela += f"""
            <tr>
                <td style="padding:14px; border-bottom:1px solid #2D2C3A;"><b>{curso_vaga}</b></td>
                <td style="padding:14px; border-bottom:1px solid #2D2C3A; color:#FF5252; font-weight:bold;">{prazo}</td>
                <td style="padding:14px; border-bottom:1px solid #2D2C3A; text-align:center;">{btn_link}</td>
            </tr>
            """
    else:
        linhas_tabela = f"""
        <tr>
            <td colspan="3" style="padding:20px; text-align:center; color:#A0A0B0;">
                Nenhuma vaga prestes a vencer nos próximos {dias_limite} dias! 
            </td>
        </tr>
        """

    html_quadro_urgencia = f"""
    <style>
        .quadro-container {{
            font-family: 'Segoe UI', sans-serif;
            background-color: #17161F;
            padding: 24px;
            border-radius: 16px;
            color: #E8E8EE;
        }}
        .tabela-urgente {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 16px;
        }}
        .tabela-urgente th {{
            text-align: left;
            padding: 12px 14px;
            background-color: #22202E;
            color: #9E9EAE;
            font-size: 12px;
            text-transform: uppercase;
        }}
    </style>

    <div class="quadro-container">
        <h3 style="margin:0; color:#FFFFFF;"> Vagas Perto de Vencer (Próximos {dias_limite} dias)</h3>
        <table class="tabela-urgente">
            <thead>
                <tr>
                    <th>Curso / Vaga</th>
                    <th>Data Limite</th>
                    <th style="text-align:center;">Link da Página</th>
                </tr>
            </thead>
            <tbody>
                {linhas_tabela}
            </tbody>
        </table>
    </div>
    """

    st.markdown(html_quadro_urgencia, unsafe_allow_html=True)
