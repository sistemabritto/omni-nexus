"""A esteira escreve dentro da tese, com metadado e link interno.

Estes testes existem por uma medição, não por preferência de estilo. Em
02/09/2026 a auditoria editorial leu os 76 artigos publicados no blog e contou:

- 0 mencionavam "Vibe Seller" ou "Vibe Coder";
- 0 citavam JURISMART, Voice Dream, Laboratório de Insights ou Omni Nexus;
- 0 falavam de comoditização, moat, licenciamento ou equity;
- 0 apontavam para outro artigo do blog (zero links internos em 76 páginas);
- 1 de 76 tinha meta_title, 2 de 76 tinham meta_description;
- 2 de 76 tinham qualquer tag, com 11 das 18 tags existentes sem nenhum post.

Nada disso é acidente de um artigo ruim: é a saída fiel de um prompt que
descrevia a empresa como "vende automação e operação com IA para donos de
empresa". O blog virou o catálogo de ferramentas que o prompt pediu. Corrigir
artigo por artigo sem corrigir o prompt reconstrói o mesmo blog em 25 dias,
no ritmo de 3 posts por dia.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "dashboard" / "backend"))

import escritor_de_artigo as ea


# --- pilar ---------------------------------------------------------------

def test_pilar_cobre_os_tres_eixos_da_tese():
    assert ea.pilar_de("quanto custa chatbot de ia para empresa") == "RASTREAR"
    assert ea.pilar_de("como criar um bot para whatsapp") == "VIBE CODAR"
    assert ea.pilar_de("como aumentar margem com automação") == "MONETIZAR"


def test_pilar_tem_briefing_proprio_para_cada_eixo():
    for nome in ("RASTREAR", "VIBE CODAR", "MONETIZAR"):
        assert ea.PILARES[nome].strip()


# --- funil ---------------------------------------------------------------

def test_infra_vai_para_vps_e_nao_para_a_call_de_prd():
    # /vps e /zapclub existem no site e receberam 0 links em 76 artigos.
    # Pauta de servidor caía em /sistema, que vende escopo, não máquina de pé.
    assert ea.funil_de("quanto custa uma vps para hospedar meu sistema") == "vps"
    assert ea.funil_de("servidor caindo toda semana") == "vps"


def test_comunidade_vai_para_zapclub():
    assert ea.funil_de("comunidade de ia para negócios") == "zapclub"


def test_funis_antigos_nao_mudaram_de_destino():
    # As rotas que já funcionavam continuam onde estavam: a auditoria não pode
    # custar a atribuição que a esteira já tinha.
    assert ea.funil_de("automação de whatsapp") == "whatsapp"
    assert ea.funil_de("roteiro para reels") == "socialjobs"
    assert ea.funil_de("gerar leads com inteligência artificial") == "sistema"


def test_todo_funil_tem_url_e_descricao():
    for slug, (url, desc) in ea.FUNIS.items():
        assert url.startswith("https://sistemabritto.com.br/")
        assert desc.strip(), slug
        assert slug in ea.ANCORA_POR_FUNIL


# --- prompt --------------------------------------------------------------

def test_prompt_carrega_a_tese_e_os_casos_reais():
    p = ea.montar_prompt({"keyword": "como automatizar cobrança"})
    assert "RASTREAR" in p and "VIBE CODAR" in p and "MONETIZAR" in p
    assert "Vibe Seller" in p and "Vibe Coder" in p
    assert "JURISMART" in p
    assert "Omni Nexus" in p


def test_prompt_nunca_escreve_jurispet():
    # O nome errado apareceu no briefing original e não pode voltar por engano.
    p = ea.montar_prompt({"keyword": "gerador de petições com ia"})
    assert "jurispet" not in p.lower()


def test_prompt_proibe_inventar_metrica_para_os_casos():
    p = ea.montar_prompt({"keyword": "como reduzir custo de suporte"})
    assert "PROIBIDO inventar" in p


def test_prompt_pede_metadados_como_campos_separados():
    p = ea.montar_prompt({"keyword": "quanto custa chatbot de ia"})
    assert "meta_title" in p and "meta_description" in p
    assert str(ea.LIMITE_META_TITLE) in p


def test_prompt_manda_o_pilar_como_primeira_tag():
    p = ea.montar_prompt({"keyword": "quanto custa chatbot de ia"})
    assert "rastrear" in p


def test_links_internos_entram_no_prompt_quando_ha_candidatos():
    p = ea.montar_prompt(
        {"keyword": "como integrar whatsapp"},
        relacionados=[{"slug": "post-a", "titulo": "Post A"},
                      {"slug": "post-b", "titulo": "Post B"}],
    )
    assert "blog.sistemabritto.com.br/post-a/" in p
    assert "LINKS INTERNOS OBRIGATÓRIOS" in p


def test_sem_candidatos_o_prompt_nao_pede_link_interno():
    # Blog vazio ou Ghost fora do ar não pode fazer o modelo inventar URL.
    p = ea.montar_prompt({"keyword": "como integrar whatsapp"}, relacionados=[])
    assert "LINKS INTERNOS OBRIGATÓRIOS" not in p


def test_lista_de_relacionados_e_limitada():
    muitos = [{"slug": f"p{i}", "titulo": f"P{i}"} for i in range(30)]
    p = ea.montar_prompt({"keyword": "x"}, relacionados=muitos)
    assert p.count("blog.sistemabritto.com.br/p") == ea.MAXIMO_DE_RELACIONADOS


# --- metadados -----------------------------------------------------------

def test_meta_title_cai_no_titulo_cortado_na_palavra():
    longo = "Como reduzir custo de atendimento sem perder vendas usando IA na operação"
    saida = ea._meta_title({}, longo)
    assert len(saida) <= ea.LIMITE_META_TITLE
    assert saida in longo and not saida.endswith(" ")


def test_meta_title_do_modelo_vence_quando_cabe():
    assert ea._meta_title({"meta_title": "Chatbot de IA: quanto custa"}, "T") == \
        "Chatbot de IA: quanto custa"


def test_meta_title_longo_do_modelo_e_descartado():
    saida = ea._meta_title({"meta_title": "x" * 90}, "Título curto")
    assert saida == "Título curto"


def test_meta_description_vazia_continua_vazia():
    # Vazia é aceitável: o Ghost cai no excerpt, que a esteira preenche.
    assert ea._meta_description({}, "Título") == ""


def test_meta_description_longa_e_cortada_no_limite():
    saida = ea._meta_description({"meta_description": "palavra " * 60}, "T")
    assert len(saida) <= ea.LIMITE_META_DESCRIPTION + 1


def test_metadado_nao_sai_com_travessao():
    saida = ea._meta_title({"meta_title": "Chatbot — quanto custa"}, "T")
    assert "—" not in saida


def test_tags_comecam_pelo_pilar_e_nao_duplicam():
    tags = ea._tags({"tags": ["WhatsApp", "IA Aplicada", "whatsapp"]},
                    "quanto custa chatbot")
    assert tags[0] == "rastrear"
    assert tags == list(dict.fromkeys(tags))
    assert len(tags) <= 4


def test_tags_existem_mesmo_sem_o_modelo_devolver_nenhuma():
    # 74 dos 76 artigos publicados saíram sem tag nenhuma. O pilar entra por
    # código justamente para que a navegação nunca dependa do modelo lembrar.
    assert ea._tags({}, "como criar um agente") == ["vibe-codar"]


def test_vocabulario_de_venda_nao_decide_pilar():
    # Mesma armadilha de "lead" em funil_de: palavra que aparece nos três
    # pilares não pode ser critério de nenhum. Com "vendas" dentro de
    # MONETIZAR, o backfill de 02/09/2026 rotulou "segurança de dados em
    # automação de vendas" como MONETIZAR, que é VIBE CODAR.
    assert ea.pilar_de("segurança de dados em automação de vendas") == "VIBE CODAR"
    assert ea.pilar_de("como automatizar vendas pelo whatsapp") == "VIBE CODAR"
    # O termo econômico específico continua decidindo.
    assert ea.pilar_de("como aumentar margem com automação") == "MONETIZAR"
    assert ea.pilar_de("como recuperar receita perdida") == "MONETIZAR"


def test_titulo_curto_prefere_fronteira_natural():
    assert ea.titulo_curto("Segurança de dados em automação de vendas: como proteger "
                           "clientes sem travar o faturamento") == \
        "Segurança de dados em automação de vendas"


def test_titulo_curto_recusa_fronteira_curta_demais():
    # "Agente de IA WhatsApp" tem 21 caracteres: cabe, mas desperdiça a linha
    # do resultado de busca. Sem meta_title, o buscador recebe o título inteiro
    # e corta onde quiser, o que informa mais.
    assert ea.titulo_curto("Agente de IA WhatsApp: como colocar um assistente real "
                           "atendendo seus clientes hoje") == ""


def test_titulo_curto_recusa_corte_no_meio_da_frase():
    # "Como estruturar a governança de IA em atendimento via" é pior que campo
    # vazio: sem meta_title o Ghost entrega a frase inteira ao buscador.
    assert ea.titulo_curto("Como estruturar a governança de IA em atendimento "
                           "via WhatsApp sem travar a operação") == ""


def test_titulo_curto_devolve_o_titulo_quando_ja_cabe():
    assert ea.titulo_curto("Quanto custa um chatbot?") == "Quanto custa um chatbot?"
