// Final user transcripts only. Local retrieval does not send provider/model messages.
export function isFileLookupRequest(text:string):boolean {
  const value=text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase()
  return /\b(arquivo|arquivos|documento|documentos|roteiro|roteiros|relatorio|relatorios)\b/.test(value)
    && /\b(busca\w*|encontr\w*|localiz\w*|consult\w*|mostr\w*|envi\w*|abr\w*|aces\w*|leia|ler|link|onde|cade|qual|quais|tem|ver|veja|manda\w*)\b/.test(value)
}
