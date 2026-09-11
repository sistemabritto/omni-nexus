#!/usr/bin/env python3
"""Build reviewable editorial artifacts; never activate campaigns or publish Reels."""
import argparse
import html
import json
import runpy
import re
from collections import Counter
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'assets/strategy'
REELS = runpy.run_path(str(OUT / 'gambito_reels_v4.py'))['REELS']
CSS = '''
:root{color-scheme:light dark;--bg:#f5f5ef;--fg:#192624;--card:#fff;--line:#d5ded6;--accent:#137351}
@media(prefers-color-scheme:dark){:root{--bg:#101916;--fg:#e8eee9;--card:#182720;--line:#354a3f;--accent:#83dcb0}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:17px/1.65 system-ui,sans-serif;overflow-wrap:anywhere}
main{max-width:1000px;margin:auto;padding:28px 20px 80px}h1{font-size:clamp(2rem,6vw,3.6rem);line-height:1.1}h2{line-height:1.25}a{color:var(--accent)}
article,section{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:24px;margin:22px 0}blockquote{border-left:4px solid var(--accent);margin:20px 0;padding-left:18px;font-size:1.2em}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace;background:var(--bg);padding:18px;border-radius:10px}small,.meta{opacity:.8}li{margin:8px 0}.tag{font:13px ui-monospace,monospace;color:var(--accent)}details{border-top:1px solid var(--line);padding-top:16px}summary{cursor:pointer;font-weight:600}nav{display:flex;flex-wrap:wrap;gap:12px}a.button{display:inline-block;padding:10px 16px;border:1px solid var(--accent);border-radius:8px}
'''
def e(value): return html.escape(str(value), quote=True)
def page(title, body):
    return f'<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{e(title)}</title><style>{CSS}</style><main><p class="tag">SISTEMA BRITTO / GAMBITO DE VALOR / V4 · 10 SET 2026</p><h1>{e(title)}</h1>{body}</main></html>'

RESOURCES = {
 'MAPA': ('Ficha do gargalo', 'as três perguntas e a ficha para escolher o primeiro gargalo', [
 'Quando esse problema aconteceu pela última vez? Descreva um episódio, não uma impressão.',
 'Quem precisou parar o trabalho e o que fez para resolver? Identifique também quem decide a compra.',
 'Qual alternativa vocês já usam e o que justificaria trocar? Não confunda interesse em IA com necessidade.',
 'Preencha: pessoa afetada / episódio / frequência observada / tempo ou custo com origem / alternativa atual / responsável / resultado desejado.',
 'Escolha UM gargalo: recorrência, impacto verificável e alguém disposto a testar. Se faltam dados, a próxima ação é conversar, não comprar software.']),
 'PROVA': ('Teste de utilidade', 'a ficha para testar utilidade antes de prometer um resultado', [
 'Escreva uma tarefa real e como ela é feita hoje. Use dados fictícios ou anonimizados na demonstração.',
 'Combine com o responsável o critério de aceite antes do teste: por exemplo, gerar um orçamento de teste com os campos obrigatórios corretos.',
 'Registre: situação atual / mudança proposta / critério / resultado observado / exceções / custo de manter / próximo responsável.',
 'Uma demo não valida segurança, escala ou retorno financeiro. Liste o que ainda precisa ser validado antes da implantação.',
 'Decida: parar, ajustar ou testar em escopo controlado. Só publique números de clientes com evidência e autorização.']),
 'INFRA': ('Checklist de operação', 'o checklist de backup, acesso e custo de operação', [
 'Backup: o que é copiado, onde fica, frequência, retenção, acesso e data do último teste de restauração isolado.',
 'Acesso: responsáveis identificados, permissões mínimas, autenticação e processo de revogação. Nunca compartilhe senhas pelo formulário.',
 'Operação: quem recebe alertas, quem atualiza, janela de manutenção e procedimento de recuperação.',
 'Custo total mensal: servidor + serviços + armazenamento + suporte + horas de manutenção. Separe estimativas de faturas reais.',
 'Antes de migrar: inventário, cópia verificável, plano de retorno e teste fora da produção. Não apague o ambiente atual para testar backup.']),
 'CONTEUDO': ('Perguntas que viram pauta', 'dez perguntas e uma ficha para transformar dúvidas em vídeos', [
 '1. Quanto custa? 2. O que muda o orçamento? 3. Quanto tempo leva? 4. Quando não vale a pena? 5. O que preciso preparar?',
 '6. Quem cuida depois? 7. Como sei que funcionou? 8. O que acontece se falhar? 9. Qual alternativa já tenho? 10. Qual é o primeiro passo?',
 'Ficha: uma pergunta real / quem decide / erro comum / exemplo demonstrável / resposta útil / próximo passo coerente.',
 'Gancho visual: mostre o objeto ou a tarefa. Falado: abra pela dúvida. Headline: curiosidade específica sem prometer algo que o vídeo não entrega.',
 'Grave a resposta com começo, exemplo e conclusão. Se pedir comentário para entregar material, prepare e teste esse material antes de postar.']),
 'FUNIL': ('Checklist do caminho até a venda', 'o checklist para encontrar onde a conversa deixa de avançar', [
 'Desenhe: Reel → comentário válido → DM entregue → clique → cadastro → conversa qualificada → checkout → pagamento confirmado.',
 'Registre por etapa: fonte, período, numerador, denominador e identidade consentida quando disponível. Métrica ausente não é zero.',
 'Teste com conta autorizada: gatilho correto, só um envio, link abrindo no celular, recompensa prometida visível e próximo passo claro.',
 'Se há 65 visitas e um clique no mesmo recorte, isso é 1,54% de cliques por visita; não prova sozinho defeito na isca nem mede vendas. Investigue também intenção e rastreamento.',
 'Mude uma variável por teste: promessa, posição do CTA ou formulário. Compare janelas equivalentes; não atribua venda sem confirmação do pagamento.']),
}
ALTS = [
 'Duas propostas podem resolver exatamente o problema errado.', 'O cliente viu sua demo. Mas conseguiu enxergar a tarefa dele ali?',
 'Antes de escolher a IA, eu faria três perguntas sobre a operação.', 'Instalar é uma etapa. Operar é outra conversa.',
 'Responder em segundos não resolve uma conversa sem direção.', 'Seu cliente acabou de te dar uma pauta. Você percebeu?',
 'Setenta usuários não salvaram o meu produto.', 'A próxima assinatura pode estar cobrindo um processo que ninguém definiu.',
 'Dois meses para construir não significam dois meses para validar um negócio.', 'Se a sua oferta cabe em qualquer empresa, talvez ela ainda esteja ampla demais.',
 'Você sabe se consegue recuperar o backup ou só sabe que ele foi feito?', 'A alternativa ao seu produto pode já estar aberta no navegador do cliente.',
 'Sua proposta explica o preço ou só lista entregas?', 'Quem mantém essa ferramenta depois que o tutorial acaba?',
 'Qual projeto merece entrar na sua operação primeiro?', 'Um gargalo fica mais claro quando você pede um episódio, não uma opinião.',
 'O projeto travou? Talvez o próximo teste esteja grande demais.', 'Eu chamo essa mudança de ordem de Gambito de Valor.',
 'Sem licença não significa sem custo de operação.', 'Você aprendeu a construir. O comprador entendeu o que comprar?',
 'Indicação boa também precisa de um próximo passo.', 'O suporte resolve melhor o que consegue reproduzir.',
 'Seu perfil ganhou seguidores. O caminho até a compra está visível?', 'Preço baixo não corrige uma proposta sem escopo.',
 'Antes de comparar preços de sistemas, compare o que será aceito como pronto.', 'A tarefa repetida pode esconder um custo que ninguém registrou.',
 'Um prompt melhora quando você consegue explicar como vai testar a resposta.', 'Vender antes de construir não é prometer qualquer coisa.',
 'Nem toda gravação sai de primeira. Esta aqui é um exemplo.', 'Seu bot sabe onde buscar a resposta certa?',
 'Antes do Sprint, você consegue explicar o que precisa entrar no projeto?', 'Mais ferramentas ou menos tarefas esquecidas?',
 'O comentário pediu um material. A mensagem entregou o quê?', 'Quatro vídeos por dia precisam de processo, não só de disposição.',
 'Quando o gargalo está claro, a conversa sobre implementação muda.',
]

def build(reward_url):
    assert len(REELS) == len(ALTS) == 35
    assert {r[0] for r in REELS} == set(range(1,36))
    reward = '<p>Um caderno prático, sem cadastro obrigatório. Escolha a ficha que corresponde à sua dúvida. Os exemplos são critérios de trabalho, não promessa de resultado.</p><nav>'
    reward += ''.join(f'<a href="#{k}">{e(v[0])}</a>' for k,v in RESOURCES.items()) + '</nav>'
    for key,(name,_,items) in RESOURCES.items():
        reward += f'<section id="{key}"><h2>{e(name)}</h2><ol>' + ''.join(f'<li>{e(x)}</li>' for x in items) + '</ol></section>'
    reward += '<section><h2>Quer transformar isso em escopo?</h2><p>A Sessão de Start é uma oferta paga para organizar prioridades e o PRD do projeto. Não inclui a implementação. Consulte condições e horários na página; avançar é opcional.</p><a class="button" href="https://www.sistemabritto.com.br/sessao-de-start?utm_source=instagram&amp;utm_medium=material&amp;utm_campaign=gambito_v4">Conhecer a Sessão de Start</a></section>'
    token=reward_url.rstrip('/').split('/')[-1].split('?')[0]
    public_base=reward_url.split('/share/')[0]
    destination='https://www.sistemabritto.com.br/sessao-de-start?'+urlencode(dict(utm_source='instagram',utm_medium='material',utm_campaign='gambito_v4'))
    tracked=public_base+'/api/shares/'+token+'/click?'+urlencode({'to':destination,'label':'gambito_v4_caderno_laser'})
    reward=reward.replace('href="https://www.sistemabritto.com.br/sessao-de-start?utm_source=instagram&amp;utm_medium=material&amp;utm_campaign=gambito_v4"',f'target="_blank" rel="noopener" href="{e(tracked)}"')
    (OUT/'caderno-gambito-v4.html').write_text(page('O próximo movimento da sua empresa', reward))
    inventory=[]; cards=[]
    for r, alt in zip(REELS, ALTS):
        n,theme,audience,pillar,stage,structure,visual,headline,hook,beats,key,revision=r
        rid=f'GV4-{n:02d}'
        utm=urlencode(dict(utm_source='instagram',utm_medium='comment_dm',utm_campaign='gambito_v4',utm_content=rid))
        if key=='LASER':
            url='https://www.sistemabritto.com.br/sessao-de-start?'+utm
            gift='as condições e os horários da Sessão de Start, uma oferta paga de diagnóstico e PRD'
            cta='Quer organizar prioridades e sair com o PRD do seu projeto? Comenta LASER para conhecer a Sessão de Start. É uma consultoria paga; a implementação é uma próxima etapa.'
        else:
            assert key in RESOURCES
            # Share wrapper does not forward fragments to its iframe. Link to
            # the public HTML endpoint so each reward opens at its actual section.
            url=public_base+'/api/shares/'+token+'/view?'+utm+'#'+key
            gift=RESOURCES[key][1]
            cta=f'Para aplicar isso na sua empresa, comenta {key}. Eu te mando {gift}.'
        dm=f'Aqui estão {gift}: {url}'
        prompt=f'''Prepare em RASCUNHO a campanha {rid} — {theme}, conta @sistemabritto.
Público: {audience}. Gatilho: {key}; confirme a normalização suportada.
Escopo somente media_id=PENDENTE. Nunca usar todos os posts como substituto. Verifique colisões, inclusive o gatilho 17, sem alterar campanhas anteriores.
Resposta pública após processamento válido: “Vou te mandar os detalhes por DM.” Não afirmar entrega sem confirmação.
Primeira DM: {dm}
Após a entrega, pergunta opcional: “Você decide sobre isso na sua empresa ou implementa para clientes?”
Não exigir seguir o perfil. Não ativar sequência automática nem mensagens em massa.
Confirme conta, token, webhook, worker, elegibilidade e limites reais; deduplique por evento/pessoa.
QA com conta autorizada: comentário → uma resposta → uma DM → URL correta e recompensa acessível. UTM não é, por si só, evidência de clique ou venda.
Vincule o media_id depois da publicação. Só ative com autorização e escopo conferido; não publique o vídeo.
Retorne campaign_id, estado, escopo, textos, links e evidência do teste. Sem teste real: NÃO VALIDADO.'''
        words=len((' '.join([hook,*beats,cta])).split()); seconds=round(words/2.5)
        cursor=0; segments=[]
        labels={'CRESA':['Reconhecimento','Erro','Solução'], 'COBA':['Oportunidade','Benefício'], 'NPPC':['Procedência','Primeira vitória'], 'AIDA':['Interesse','Desejo'], 'ISAC':['Sentimento','Alívio e consequência'], 'DDC':['Dualidade','Curiosidade'], 'AAA':['Amplie']}[structure]
        assert len(labels)==len(beats), (rid,structure)
        for label, text in [('Gancho A',hook), *list(zip(labels,beats)), ('Ação',cta)]:
            end=cursor+max(3,round(len(text.split())/2.5))
            segments.append(f'<p><b>{cursor}–{end}s · {label}</b><br>{e(text)}</p>');cursor=end
        item=dict(id=rid,theme=theme,audience=audience,pillar=pillar,stage=stage,structure=structure,visual=visual,headline=headline,hooks=[hook,alt],beats=beats,cta=cta,reward=key,url=url,openreply_prompt=prompt,status='draft_review',campaign_id=None,media_id=None,revision=revision)
        inventory.append(item)
        cards.append(f'''<article id="{rid}"><p class="tag">{rid} · DIA {(n-1)//5+1} / SLOT {(n-1)%5+1} · RASCUNHO PARA REVISÃO</p><h2>{e(theme)}</h2>
<p class="meta">Público: {audience} · {pillar} · {stage} · Estrutura de Linguagem: {structure}</p>
<p><b>Hipótese:</b> a situação concreta ajuda este público a reconhecer o gargalo e escolher o próximo passo. Validar com comentários qualificados e avanço no funil, não apenas alcance.</p>
<p><b>Gancho visual · 1–3s:</b> {e(visual)}</p><blockquote>{e(headline)}</blockquote>
<p><b>Headline:</b> abre uma dúvida específica; a resposta vem no desenvolvimento. Polêmica não é obrigatória e não autoriza exagero.</p>
<p><b>Gancho falado B:</b> {e(alt)}</p><h3>Fala sugerida · cerca de {seconds}s</h3><p class="meta">Tempos estimados a 150 palavras/minuto. Use A ou B, nunca os dois. Mantenha a cena inicial e mostre o exemplo durante a explicação; leitura de ensaio define o corte final.</p>
{''.join(segments)}<p><b>Legenda:</b> {e(headline)} {e(cta)}</p>
<p><b>Destino:</b> <a href="{e(url)}">{e(gift)}</a></p>
<p><b>Evidência e revisão:</b> {e(revision)} Recomendações de processo são hipóteses de trabalho; relatos pessoais citados precisam da confirmação de Felipe antes de gravar.</p>
<details><summary>Prompt OpenReply pronto para copiar</summary><pre>{e(prompt)}</pre></details>
<p><b>Antes de postar:</b> fala e prova aprovadas; material abre no celular; teste autorizado concluído; media_id vinculado; campanha autorizada. Nesta entrega, nenhuma campanha foi criada ou ativada.</p></article>''')
    introduction='<p>35 fichas reescritas. Proposta de sete dias com quatro vídeos-base e um quinto opcional por dia; início sugerido em 11/09. Ainda não são publicações nem campanhas ativas.</p><p>O objetivo é aumentar a frequência sem perder congruência: uma pessoa, um problema, uma pequena resposta útil e um próximo passo. Valide os primeiros oito roteiros antes de gravar o lote inteiro.</p><nav>'
    introduction+=''.join(f'<a href="#GV4-{n:02d}">{n:02d}</a>' for n in range(1,36))+'</nav>'
    (OUT/'roteiros-gambito-v4.html').write_text(page('35 Reels · Gambito de Valor',introduction+''.join(cards)))
    (OUT/'gambito-v4-inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))
    counts=Counter(r[2] for r in REELS)
    editorial=f'''<p>Revisão da linha editorial e dos 35 roteiros criados anteriormente. O nome foi preservado; as promessas e o caminho comercial foram corrigidos.</p>
<section><h2>Meu veredito: manter o nome, concretizar o mecanismo</h2><p>Gambito de Valor é uma boa metáfora para abandonar a solução favorita e ganhar posição entendendo o problema do comprador. O diferencial não é ter batizado o método: é mostrar como você toma decisões melhores e provar o que entrega.</p><blockquote>Vibe coder constrói. Vibe Seller joga o Gambito de Valor.</blockquote><p>Para quem ainda não conhece sua narrativa: <b>Abra mão da ideia favorita. Resolva um problema que já custa caro.</b></p><p>Eu retiraria “venda sem esforço”, “único caminho” e “impossível copiar”. Essas promessas enfraquecem justamente a credibilidade que um decisor precisa para contratar.</p></section>
<section><h2>Três jogadas com uma saída verificável</h2><ol><li><b>Rastrear:</b> suspender a solução favorita e investigar episódio, pessoa, frequência e alternativa atual. Entrega: ficha do gargalo.</li><li><b>Vibe codar:</b> testar utilidade em escopo pequeno, com critério e custo de operação. Entrega: prova de utilidade, não promessa de escala.</li><li><b>Monetizar:</b> proposta, decisor, implantação, adoção e acompanhamento. Entrega: resultado medido; uma demo não é uma venda.</li></ol></section>
<section><h2>Quem deve se reconhecer</h2><p>O dono compra melhoria na empresa, não a identidade de programador. O prestador quer transformar capacidade de construir em oferta. Escolha um por Reel; use o nome do método depois do problema concreto.</p><p>Este lote: {counts['dono']} para donos/gestores, {counts['prestador']} para prestadores e {counts['ponte']} de ponte/identidade. É uma hipótese editorial, não uma segmentação comprovada pela auditoria.</p><p>Nome sugerido para testar: <b>Felipe Britto | IA para empresas</b>. Preserve Vibe Seller como assinatura da narrativa. Bio proposta: “Rastreie gargalos. Transforme IA em resultado. 🎯<br>Sistemas para vendas e operação. ⚡<br>Eu respondo os directs. Materiais e consultoria ↓”</p><p>A bio atual tem personalidade e proximidade; o ajuste é esclarecer a aplicação empresarial, não trocar sua voz por uma descrição de agência. Compare cliques qualificados e conversas, sem atribuir a mudança só à bio.</p></section>
<section><h2>O CTA agora continua a conversa</h2><p>Diagnóstico → ficha do gargalo. Demonstração → teste de utilidade. Infra → checklist de operação. Conteúdo → perguntas e pauta. Conversão → Sessão de Start explicitamente paga.</p><p>A primeira DM entrega o prometido. O convite comercial vem depois, sem follow gate obrigatório. <a href="{e(reward_url)}">Caderno com as cinco recompensas reais</a>.</p><p>Sessão de Start: PRD, prioridades e escopo; Sprint/Implementação são etapas seguintes. A configuração atual registra R$150 promocionais, preço normal R$300 e crédito integral no próximo serviço. As três primeiras agendas semanais precisam de controle real: contador de tempo não prova disponibilidade. Os roteiros remetem às condições vigentes sem inventar vagas restantes.</p></section>
<section><h2>O que os 47 Reels permitem concluir</h2><p>A soma dos cards é 51.678 de alcance por post, 76.505 plays, 988 likes, 664 comentários, 925 salvamentos e 700 compartilhamentos. Não são 51.678 pessoas únicas, nem uma coleta homogênea dos últimos 30 dias.</p><p>Maior alcance: demonstração de CRM, 12.119. Segundo: meme/controvérsia, 9.131. Outra demonstração de CRM: 6.009. Portanto, a frase anterior “os dois maiores são demonstrações” estava errada. Demonstração merece teste; isso não prova venda nem superioridade causal.</p><p>Há quatro falhas de processamento e não há interpretação visual validada. Média de tempo assistido dividida pela duração não equivale a conclusão. Não usar esse conjunto para dizer em qual etapa o lead abandonou a compra.</p></section>
<section><h2>Plano de execução: 120 como base, 150 como extensão</h2><ol><li><b>Antes do primeiro lote:</b> aprovar oito fichas, confirmar relatos pessoais, testar recompensa e fluxo OpenReply com conta autorizada.</li><li><b>Diariamente:</b> quatro Reels-base; quinto só se houver material útil aprovado. Gravar em lotes e guardar oito aprovados de reserva.</li><li><b>Magneto:</b> uma pergunta por vez, duas opções concretas, ficha completa ao fechar. Brief de manhã e fechamento à noite; não chamar rascunho de publicado.</li><li><b>Após 48–72h:</b> observar retenção disponível, salvamentos/alcance e comentários qualificados em janelas comparáveis. Não declarar vencedor com um clique.</li><li><b>Semanalmente:</b> conferir DM entregue → clique → lead qualificado → consultoria paga → Sprint/Implementação. Ausência de evento é dado ausente até testar a instrumentação.</li><li><b>Decisão:</b> repetir mecanismos que combinam atenção e intenção; reduzir pautas que trazem audiência incompatível. Alterar uma variável por teste.</li></ol><p>Nenhuma postagem, campanha ou abordagem comercial foi ativada por este documento. O roteiro é uma proposta de gravação, não uma aprovação em nome de Felipe.</p></section>'''
    (OUT/'linha-editorial-gambito-v4.html').write_text(page('Gambito de Valor · linha editorial v4',editorial))

def audit(source):
    original=Path(source).read_text()
    cards=re.findall(r'<article\b.*?</article>',original,re.S)
    assert len(cards)==47
    totals={key:sum(int(re.search(r'<b>'+key+r'</b>:\s*(\d+)',card)[1]) for card in cards) for key in ['reach','likes','comments','saved','shares','plays']}
    body='<section><h2>Correção dos agregados · revisão v4</h2><p>O cabeçalho anterior não correspondia à soma dos 47 cards. Os cards abaixo foram preservados integralmente; esta revisão recalcula o resumo, sem nova coleta nem alteração das transcrições.</p><p>'+e(' · '.join(f'{k}: {v:,}'.replace(',','.') for k,v in totals.items()))+'</p><p>Alcance é soma por post, sem deduplicar pessoas. Coleta inicial em 03/09, incremental em 10/09 e atualização retroativa de watch-time: as métricas não têm todas a mesma janela. Os posts datam de 17/08 a 08/09/2026.</p></section>'
    ranking=sorted(cards,key=lambda c:int(re.search(r'<b>reach</b>:\s*(\d+)',c)[1]),reverse=True)[:3]
    body+='<section><h2>Os três maiores alcances desta amostra</h2><ol>'
    for card in ranking:
        url=re.search(r'href="(https://www.instagram.com/reel/[^"]+)"',card)[1]
        reach=re.search(r'<b>reach</b>:\s*(\d+)',card)[1]
        body+=f'<li><a href="{e(url)}">{e(url)}</a> — {reach}</li>'
    body+='</ol><p>O segundo é meme/controvérsia, não a segunda demonstração de CRM. Alcance não prova venda. Classificações editoriais são hipóteses; não houve interpretação multimodal dos frames.</p></section><section><h2>Limites e inconsistências mantidos visíveis</h2><p>43 processamentos OK e quatro falhas. Falha de processamento do vídeo não invalida automaticamente as métricas disponíveis. Plays e tempo assistido foram recuperados; segue ausente neste conjunto a atribuição de cliques, leads e vendas por Reel.</p><p>Não generalizar essa ausência como incapacidade universal de toda versão da API. A divisão tempo médio/duração é uma razão, não taxa de conclusão; pode ser afetada por replays e definições de coleta. O card Dcpbe71Nsg0 registra média de 113,05s com retenção exibida de 100%: requer conferência da fonte antes de comparar retenção. Não corrigi o card por suposição.</p><p>A média anterior de retenção (34,5%) não deve orientar ranking até essa validação. Não há prova aqui de que o Gambito já aumentou conversão. O teste novo precisa ligar conteúdo, entrega de DM, clique, conversa e pagamento.</p></section><h2>47 fichas originais preservadas</h2>'
    (OUT/'auditoria47-gambito-v4.html').write_text(page('47 Reels · auditoria revisada',body+''.join(cards)))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--reward-url',required=True);parser.add_argument('--audit-source')
    args=parser.parse_args();build(args.reward_url)
    if args.audit_source: audit(args.audit_source)
