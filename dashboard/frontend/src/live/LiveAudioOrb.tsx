import { useEffect, useRef } from 'react'
type Frame={spectrum:Uint8Array;input:number;speaking:boolean}
export default function LiveAudioOrb({frame,phase,color,onSpeaking}:{frame:()=>Frame;phase:string;color:string;onSpeaking?:(value:boolean)=>void}){
  const ref=useRef<HTMLCanvasElement>(null)
  useEffect(()=>{
    const canvas=ref.current,ctx=canvas?.getContext('2d');if(!canvas||!ctx)return
    const reduced=window.matchMedia('(prefers-reduced-motion: reduce)')
    let animation=0,last=0,wasSpeaking=false
    const draw=(time:number)=>{
      animation=requestAnimationFrame(draw)
      if(document.hidden||time-last<(reduced.matches?180:32))return
      last=time
      const {spectrum,input,speaking}=frame()
      if(speaking!==wasSpeaking){wasSpeaking=speaking;onSpeaking?.(speaking)}
      const size=720,center=size/2,radius=244;ctx.clearRect(0,0,size,size)
      ctx.strokeStyle=color;ctx.lineCap='round'
      for(let i=0;i<144;i++){
        const angle=i*Math.PI*2/144-Math.PI/2
        const bin=spectrum.length?spectrum[Math.floor((i%72)/72*spectrum.length*.65)]/255:0
        const signal=speaking?bin:input*.6
        const length=4+Math.pow(signal,.8)*62
        ctx.globalAlpha=.25+signal*.7;ctx.lineWidth=speaking?2.7:1.5
        ctx.beginPath();ctx.moveTo(center+Math.cos(angle)*radius,center+Math.sin(angle)*radius)
        ctx.lineTo(center+Math.cos(angle)*(radius+length),center+Math.sin(angle)*(radius+length));ctx.stroke()
      }
      ctx.globalAlpha=.75;ctx.lineWidth=1.3;ctx.beginPath();ctx.arc(center,center,radius-10,0,Math.PI*2);ctx.stroke()
      ctx.globalAlpha=.16;ctx.lineWidth=1;ctx.beginPath();ctx.arc(center,center,radius-30,0,Math.PI*2);ctx.stroke()
    }
    animation=requestAnimationFrame(draw)
    return()=>{cancelAnimationFrame(animation);onSpeaking?.(false)}
  },[frame,color,onSpeaking])
  return <div className="live-orb" data-phase={phase} style={{'--agent-color':color} as React.CSSProperties}>
    <div className="live-orb-halo"/><canvas ref={ref} width={720} height={720} aria-hidden="true"/>
    <div className="live-orb-brand" aria-label="OmniNexus Live"><span>OMNI<span className="live-brand-dot">·</span></span><strong>NEXUS</strong><small>LIVE</small></div>
  </div>
}
