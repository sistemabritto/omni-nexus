> Adaptado pelo OmniNexus em 2026-10-15 de MarketingSkills; Copyright (c) 2025 Corey Haines, MIT. Fontes e modificações em ../ORIGIN.md.

# Dex — plano de eventos e fonte da verdade

Definir pergunta de decisão antes de instrumentação. Funil proposto: CTA → quiz iniciado/concluído → lead persistido → lead qualificado → oportunidade → venda. Definir cada estágio por evidência do sistema real, responsável e critério, sem confundir clique com lead salvo ou pagamento com apenas intenção.

Ficha por evento: nome canônico existente ou proposto, trigger, origem, ID opaco estável, chave de dedup, campanha/hipótese, timestamp/fuso e propriedades estritamente necessárias. Não enviar PII, respostas livres do quiz, e-mail, telefone ou dados sensíveis a URLs/UTMs/analytics. IDs pseudônimos também precisam de minimização e controle; não assumir que hash libera uso irrestrito.

CRM/backend acordado é fonte da verdade para lead/oportunidade/venda; ledger deduplicado conta cada conversão uma vez. Analytics explica comportamento, não redefine vendas. Backend só emite lead salvo após persistência confirmada. Distinguir eventos de tentativa e sucesso; retries não inflam métricas. Conferir totais com agregação independente e rastrear discrepâncias até os registros.

Plano não é tracking instalado. Só marcar evento validado após observar emissão, payload sem PII, dedup e conciliação no ambiente autorizado. Sem dados, entregar dicionário e validação pendente; não buscar credenciais nem alterar GA4/GTM/CRM neste lote.
