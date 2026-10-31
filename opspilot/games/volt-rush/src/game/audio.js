// 100% original Web Audio synthesis. No sampled audio, music loops or third-party licenses.
export class Sound {
  constructor(){this.context=null;this.engine=null;this.gain=null;this.enabled=true;this.master=null;this.lastEvent=0;}
  initialize(){
    if(!this.enabled)return;
    try{
      const AC=window.AudioContext||window.webkitAudioContext;if(!AC)return;
      if(!this.context){
        this.context=new AC();this.master=this.context.createGain();this.master.gain.value=.24;this.master.connect(this.context.destination);
        this.engine=this.context.createOscillator();this.engine.type='sawtooth';this.gain=this.context.createGain();
        const filter=this.context.createBiquadFilter();filter.type='lowpass';filter.frequency.value=480;
        this.engine.connect(filter);filter.connect(this.gain);this.gain.connect(this.master);this.gain.gain.value=.0001;this.engine.start();
      }
      if(this.context.state==='suspended')this.context.resume();
    }catch(e){console.warn('Audio unavailable',e);}
  }
  tone(hz=400,duration=.12,kind='sine',volume=.14,end=hz*.7,delay=0){
    if(!this.enabled||!this.context)return;
    const ctx=this.context,t=ctx.currentTime+delay,osc=ctx.createOscillator(),gain=ctx.createGain();
    osc.type=kind;osc.frequency.setValueAtTime(Math.max(1,hz),t);osc.frequency.exponentialRampToValueAtTime(Math.max(1,end),t+duration);
    gain.gain.setValueAtTime(.0001,t);gain.gain.linearRampToValueAtTime(volume,t+.012);
    gain.gain.exponentialRampToValueAtTime(.0001,t+duration);
    osc.connect(gain);gain.connect(this.master);osc.start(t);osc.stop(t+duration+.03);
  }
  // White noise burst synthesized directly via an AudioBuffer, not a downloaded recording.
  noise(duration=.26,volume=.11,filterFrequency=1250){
    if(!this.enabled||!this.context)return;const ctx=this.context,t=ctx.currentTime;
    const size=Math.max(1,Math.floor(ctx.sampleRate*duration)),buffer=ctx.createBuffer(1,size,ctx.sampleRate),data=buffer.getChannelData(0);
    for(let i=0;i<size;i++)data[i]=(Math.random()*2-1)*(1-i/size);
    const src=ctx.createBufferSource(),filter=ctx.createBiquadFilter(),gain=ctx.createGain();
    filter.type='lowpass';filter.frequency.value=filterFrequency;
    gain.gain.setValueAtTime(volume,t);gain.gain.exponentialRampToValueAtTime(.0001,t+duration);
    src.buffer=buffer;src.connect(filter);filter.connect(gain);gain.connect(this.master);src.start(t);src.stop(t+duration);
  }
  play(event){
    if(!this.enabled)return;
    switch(event){
      case 'tick': this.tone(550,.13,'sine',.2,470);break;
      case 'go':this.tone(700,.16,'triangle',.22,1120);this.tone(990,.35,'triangle',.24,1500,.13);break;
      case 'pickup':this.tone(520,.12,'triangle',.16,980);this.tone(870,.19,'sine',.17,1510,.09);break;
      case 'boost':this.noise(.35,.065,3200);this.tone(110,.39,'sawtooth',.11,790);this.tone(360,.3,'triangle',.14,850,.04);break;
      case 'shield':this.tone(380,.29,'sine',.19,1040);this.tone(770,.4,'triangle',.16,1390,.1);break;
      case 'pulse':this.tone(1150,.23,'sawtooth',.14,190);this.noise(.23,.09,4200);break;
      case 'oil':this.tone(380,.12,'square',.13,160);this.tone(200,.16,'triangle',.09,100,.11);break;
      case 'drift':this.tone(980,.10,'triangle',.09,1250);break;
      case 'hit':this.noise(.33,.13,900);this.tone(240,.32,'sawtooth',.18,60);break;
      case 'finish':for(let i=0;i<4;i++)this.tone([660,880,1100,1440][i],.32,'triangle',.17,[880,1120,1400,1880][i],i*.13);break;
    }
  }
  update(speed){if(!this.context||!this.gain)return;const now=this.context.currentTime;
    this.engine.frequency.setTargetAtTime(58+speed*4.1,now,.07);
    this.gain.gain.setTargetAtTime(this.enabled?.035+Math.min(30,Math.abs(speed))*.0027:.0001,now,.1);
  }
  mute(){this.enabled=!this.enabled;if(this.context)this.master.gain.setTargetAtTime(this.enabled?.24:0,this.context.currentTime,.03);return this.enabled;}
}
