import json,html
from pathlib import Path
root=Path(__file__).parent
rows=json.loads((root/'route-results.json').read_text())
lines=['<!doctype html><html lang="pt-BR"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Cobertura visual OmniNexus Live</title><style>body{background:#080b12;color:#e2e8f0;font:15px system-ui;margin:24px}a{color:#a3ff12}section{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:20px}article{background:#101722;padding:16px;border:1px solid #344054;border-radius:12px}img{width:100%;height:260px;object-fit:contain;object-position:top}small{display:block;color:#b8c5d6}</style><h1>OmniNexus Live · cobertura de rotas</h1><p>App local com fixtures de QA. Capturas de estados vazios/erro não comprovam serviços reais ou prontidão de voz.</p><section>']
for r in rows:
 image=r.get('screenshot')
 lines.append('<article><strong>'+html.escape(r['route'])+' · '+str(r['viewport'])+'px</strong><small>'+html.escape(r['validation'])+'</small>'+('<a href="'+html.escape(image)+'"><img loading="lazy" src="'+html.escape(image)+'" alt="Captura da rota '+html.escape(r['route'])+'"></a>' if image else '<p>Sem captura</p>')+'</article>')
lines.append('</section></html>')
(root/'gallery.html').write_text('\n'.join(lines))
md=['# Matriz de cobertura','', '| Rota | 375px | 1440px |','|---|---|---|']
for route in dict.fromkeys(x['route']for x in rows):
 states={x['viewport']:x['validation']for x in rows if x['route']==route}
 md.append('| '+route+' | '+states.get(375,'não testado')+' | '+states.get(1440,'não testado')+' |')
(root/'route-matrix.md').write_text('\n'.join(md)+'\n')
