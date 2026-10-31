// Tiny original synthesis soundscape. No samples, external media, or copyright dependencies.
export class Sound {
  constructor(){this.context=null;this.engine=null;this.gain=null;this.enabled=true;this.master=null;}
  initialize(){
    if(!this.enabled)return;
    try{
      const AC=window.AudioContext||window.webkitAudioContext;
      if(!AC)return;
      if(!this.context){
        this.context=new AC();this.master=this.context.createGain();this.master.gain.value=.22;this.master.connect(this.context.destination);
        this.engine=this.context.createOscillator();this.engine.type='sawtooth';this.gain=this.context.createGain();
        const filter=this.context.createBiquadFilter();filter.type='lowpass';filter.frequency.value=400;
        this.engine.connect(filter);filter.connect(this.gain);this.gain.connect(this.master);
        this.gain.gain.value=.0001;this.engine.start();
      }
      if(this.context.state==='suspended')this.context.resume();
    }catch(e){console.warn('Audio unavailable',e);}
  }
  tone(hz=400,duration=.12,kind='sine',volume=.14,end=hz*.7){
    if(!this.enabled||!this.context)return;
    const ctx=this.context,t=ctx.currentTime,osc=ctx.createOscillator(),gain=ctx.createGain();
    osc.type=kind;osc.frequency.setValueAtTime(hz,t);osc.frequency.exponentialRampToValueAtTime(Math.max(1,end),t+duration);
    gain.gain.setValueAtTime(.0001,t);gain.gain.linearRampToValueAtTime(volume,t+.015);
    gain.gain.exponentialRampToValueAtTime(.0001,t+duration);
    osc.connect(gain);gain.connect(this.master);osc.start(t);osc.stop(t+duration+.02);
  }
  play(event){
    if(event==='tick')this.tone(550,.13,'sine',.2,470);
    if(event==='go'){this.tone(700,.16,'triangle',.22,1120);setTimeout(()=>this.tone(990,.35,'triangle',.24,1500),130);}
    if(event==='pickup'){this.tone(640,.13,'triangle',.16,1040);setTimeout(()=>this.tone(880,.15,'triangle',.13,1400),100);}
    if(event==='boost')this.tone(210,.4,'sawtooth',.14,780);
    if(event==='hit')this.tone(240,.32,'sawtooth',.22,60);
    if(event==='finish'){this.tone(880,.22,'triangle',.17,1160);setTimeout(()=>this.tone(1320,.5,'triangle',.22,1600),160);}
  }
  update(speed){if(!this.context||!this.gain)return;const now=this.context.currentTime;
    this.engine.frequency.setTargetAtTime(58+speed*4.1,now,.07);
    this.gain.gain.setTargetAtTime(this.enabled?.04+Math.min(30,Math.abs(speed))*.003:.0001,now,.1);
  }
  mute(){this.enabled=!this.enabled;if(this.context)this.master.gain.setTargetAtTime(this.enabled?.22:0,this.context.currentTime,.03);return this.enabled;}
}
