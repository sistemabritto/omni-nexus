# Dez referências de vídeo: decisão por fonte, sem ativação presumida

Complemento da auditoria. Fonte lida nesta frente: checkout do owner task-3/video-reference-catalog, HEADbe6433f, .claude/skills/video-editorial-pipeline/references/reference-catalog.md. Pin/licença ali são pesquisa do owner, não nova execução upstream por esta frente. Módulo/commit/teste abaixo identificam documentação/descoberta, não motores incorporados. Nenhum novo repo/plugin foi instalado.

| Fonte | Decisão concreta | Módulo/commit/teste e limite |
|---|---|---|
| OpenMontage | Não incorporar código/serviço; manter apenas referência conceitual | reference-catalog.md,1d8f441/be6433f; tests/media/test_media_editorial.py no owner verifica descoberta/contratos. Sem teste do motor upstream. |
| video-shotcraft | Referência de intenção de plano/produto, sem copiar pacote nem aplicar a todo bruto | Mesmo catálogo/1d8f441; teste de descoberta, sem execução upstream. |
| Hypit | Não incorporar backend/SaaS; conceitos gerais somente | Mesmo catálogo/1d8f441; condições adicionais relatadas pelo owner, nenhum runtime adotado. |
| OpenCreator | Não incorporar neste lote; identidade/pin/licença e encaixe ainda não rastreados individualmente no catálogo lido | Nenhum módulo/commit/teste de integração identificado. Não preencher lacuna com suposição de uso. |
| OpenShorts | Estudo de decomposição/QA; sem cloud/autopilot/auth/billing ou dependências novas | Mesmo catálogo/1d8f441; fonte separa core/cloud e dependências; sem execução upstream. |
| AI-Youtube-Shorts-Generator (Anil) | Referência de etapas; não reutilizar cortes até provar continuidade de timestamps | Mesmo catálogo/1d8f441; suspeita de offsets não foi reproduzida, não afirmar defeito. |
| Remotion | Manter HyperFrames como motor padrão; alternativa depende de decisão explícita | Catálogo/1d8f441; adaptador local .claude/skills-media/remotion-to-hyperframes/SKILL.md existe, mas nenhum port/render dessa integração foi executado. Não confundir licença do motor e exemplos. |
| MoneyPrinterTurbo | Aproveitar conceitualmente fronteiras de etapas/falhas, sem instalar pipeline, fontes ou músicas | Catálogo/1d8f441; documentação de direitos/módulos não comprova geração. |
| OneTake | Não incorporar código/skill; conceitos de continuidade e ritmo somente | Catálogo/be6433f explicita restrição não comercial relatada; não presumir termos Pro. Sem execução upstream. |
| ReelMimic | Referência de composição/câmera/crítica final 2D, sem instalar agente/sandbox | Catálogo/be6433f; zero bloqueios/revisão humana são conceitos, não prova de QA executado; sem promessa de Blender/3D. |

O teste do catálogo do owner não foi reexecutado nesta frente; não declarar seus testes como validação nossa do upstream. Os testes de prompts/skills desta frente verificam carregamento local. O manual39páginas/28repos/PDF/print foi confirmado pelo pai, não rebaixar “considerado” a “ativo”. A lacuna OpenCreator e a identificação de “LPUís” permanecem explícitas. Integração do catálogo do owner em produção requer confirmação do integrador, não inferida por HEAD local.
