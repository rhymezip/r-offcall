// Two copies of the actual app, connected through an in-memory signaling relay.
const checks=[];
const wait=ms=>new Promise(resolve=>setTimeout(resolve,ms));
function check(name,ok){checks.push({name,ok:!!ok});if(!ok)throw Error(name);}
async function until(fn,ms=5000){
  const end=Date.now()+ms;
  while(Date.now()<end){if(fn())return true;await wait(30);}
  return false;
}
const frames=[],timers=[],tracks=[],audioContexts=[];
async function frame(){
  const f=document.createElement('iframe');
  f.style='width:800px;height:600px';
  const loaded=new Promise(resolve=>f.onload=resolve);
  f.src='/app';document.body.appendChild(f);frames.push(f);await loaded;
  return f.contentWindow;
}
function picture(w,color){
  const canvas=w.document.createElement('canvas');canvas.width=160;canvas.height=120;
  const ctx=canvas.getContext('2d');
  const draw=()=>{ctx.fillStyle=color;ctx.fillRect(0,0,160,120);};
  draw();timers.push(setInterval(draw,50));
  const stream=canvas.captureStream(15);tracks.push(...stream.getTracks());return stream;
}
function setup(w,sid,camera=true,sharing=false){
  const a=w.testApp;
  a.dropAllPeers();a.ICE.iceServers=[];
  const stream=camera?picture(w,'rgb(240,20,20)'):new w.MediaStream();
  const audioContext=new w.AudioContext();audioContexts.push(audioContext);
  const oscillator=audioContext.createOscillator();
  const destination=audioContext.createMediaStreamDestination();
  oscillator.connect(destination);oscillator.start();
  const audio=destination.stream.getAudioTracks()[0];stream.addTrack(audio);tracks.push(audio);
  a.S.set('user',{sid,name:sid,role:'teacher',faculty:''});
  a.S.set('room',{id:'test',owner_sid:'A',members:[
    {sid:'A',name:'Alice',role:'teacher'}, {sid:'B',name:'Bob',role:'student'}
  ]});
  a.S.set('platform','Test');a.S.set('localStream',stream);
  a.S.set('screenStream',sharing?picture(w,'rgb(20,20,240)'):null);
  a.S.set('media',{cam:camera,mic:true,screen:sharing});
  a.S.set('screen','room');a.renderGrid();return a;
}
async function connect(wa,wb,{cameraA=true,cameraB=true,initiator='A',sharingA=false}={}){
  const apps={A:setup(wa,'A',cameraA,sharingA),B:setup(wb,'B',cameraB)};
  const pcs={},pending={A:[],B:[]},errors=[];
  async function iceTo(sid,candidate){
    if(pcs[sid]&&pcs[sid].remoteDescription)await pcs[sid].addIceCandidate(candidate);
    else pending[sid].push(candidate);
  }
  async function flush(sid){for(const c of pending[sid].splice(0))await pcs[sid].addIceCandidate(c);}
  for(const sid of ['A','B']){
    const other=sid==='A'?'B':'A';
    apps[sid].setSocket({connected:true,emit:(event,data)=>{
      (async()=>{
        if(event==='webrtc_ice')await iceTo(other,data.candidate);
        if(event==='webrtc_offer'){
          await pcs[other].setRemoteDescription(data.offer);await flush(other);
          await apps[other].configurePeerMedia(pcs[other]);
          await pcs[other].setLocalDescription(await pcs[other].createAnswer());
          await pcs[sid].setRemoteDescription(pcs[other].localDescription);await flush(sid);
        }
        if(event==='media_state'){
          const a=apps[other];
          a.S.upd('screenStates',{[sid]:data.screen});
          a.S.upd('camStates',{[sid]:data.cam});a.S.upd('micStates',{[sid]:data.mic});
          a.renderGrid();
        }
      })().catch(e=>errors.push(e.stack));
    }});
  }
  const responder=initiator==='A'?'B':'A';
  pcs[responder]=apps[responder].makePeer(initiator,false);
  pcs[initiator]=apps[initiator].makePeer(responder,true);
  check('offer/answer stable ('+initiator+' initiates)',await until(()=>
    pcs.A.signalingState==='stable'&&pcs.A.remoteDescription&&pcs.B.signalingState==='stable'));
  check('signaling has no errors',errors.length===0);
  for(const sid of ['A','B']){
    const p=pcs[sid];
    check(sid+' reserves distinct camera and screen senders',p.getTransceivers().length===3&&
      p.getTransceivers()[1]!==p.screenTransceiver&&p.getTransceivers()[2]===p.screenTransceiver);
    const other=sid==='A'?'B':'A';
    const cam=apps[sid].S.get('remoteStreams')[other];
    const screen=apps[sid].S.get('remoteScreenStreams')[other];
    check(sid+' routes received camera separately from screen',cam&&screen&&
      cam.getVideoTracks().length===1&&screen.getVideoTracks().length===1&&
      cam.getVideoTracks()[0]!==screen.getVideoTracks()[0]);
  }
  return {apps,pcs,errors};
}
async function share(w){
  const stream=picture(w,'rgb(20,20,240)');
  w.navigator.mediaDevices.getDisplayMedia=async()=>stream;
  await w.testApp.togScreen();await wait(80);return stream;
}
function screenLayout(w,sharer){
  const doc=w.document,main=doc.querySelector('#tile-scr video');
  return doc.getElementById('grid').classList.contains('scrmode')&&
    main&&main.srcObject===w.testApp.S.get('remoteScreenStreams')[sharer]&&
    doc.querySelectorAll('.scr-strip .tile').length===2;
}
(async()=>{
  let error;
  try{
    const wa=await frame(),wb=await frame();
    for(const initiator of ['A','B']){
      const c=await connect(wa,wb,{initiator});
      const camera=c.pcs.A.getTransceivers()[1].sender.track;
      const microphone=c.pcs.A.getTransceivers()[0].sender.track;
      for(let round=0;round<2;round++){
        const display=await share(wa);
        check('camera continues during screen share',c.pcs.A.getTransceivers()[1].sender.track===camera&&camera.readyState==='live');
        check('microphone continues during screen share',c.pcs.A.getTransceivers()[0].sender.track===microphone&&microphone.enabled);
        check('screen uses its own sender',c.pcs.A.screenTransceiver.sender.track===display.getVideoTracks()[0]);
        check('receiver shows screen and both camera tiles',screenLayout(wb,'A'));
        check('receiver camera tile uses camera stream',wb.document.querySelector('#tile-A video').srcObject===c.apps.B.S.get('remoteStreams').A);
        check('receiver labels actual sharer',wb.document.getElementById('tile-scr').textContent.includes('Alice'));
        c.apps.A.stopScreen();await wait(80);
        check('stop clears only screen sender',c.pcs.A.screenTransceiver.sender.track===null&&c.pcs.A.getTransceivers()[1].sender.track===camera);
        check('receiver returns to camera grid',!wb.document.getElementById('grid').classList.contains('scrmode'));
      }
      // Check SDP/routing/UI only: offscreen Qt may not establish a UDP path.
      // Passing this suite does not prove received video frames or hardware.
    }
    let late=await connect(wa,wb,{sharingA:true,initiator:'B'});
    late.apps.B.S.upd('screenStates',{A:true});late.apps.B.renderGrid();
    check('late join keeps camera and active screen senders',
      late.pcs.A.getTransceivers()[1].sender.track===late.apps.A.S.get('localStream').getVideoTracks()[0]&&
      late.pcs.A.screenTransceiver.sender.track===late.apps.A.S.get('screenStream').getVideoTracks()[0]);
    check('late join shows screen and both cameras',screenLayout(wb,'A'));
    late.apps.A.togCam();late.apps.A.togMic();await wait(80);
    check('camera and mic can be muted without stopping screen',
      !late.pcs.A.getTransceivers()[1].sender.track.enabled&&
      !late.pcs.A.getTransceivers()[0].sender.track.enabled&&
      late.pcs.A.screenTransceiver.sender.track.readyState==='live'&&screenLayout(wb,'A'));
    check('receiver shows avatar for disabled camera',wb.document.querySelector('#tile-A video').style.display==='none');
    late.apps.A.stopScreen();await wait(80);
    check('screen stop preserves muted camera and microphone',!late.apps.A.S.get('media').cam&&!late.apps.A.S.get('media').mic);
    const c=await connect(wa,wb,{cameraA:false});
    await share(wa);
    check('participant without camera can share independently',c.pcs.A.screenTransceiver.sender.track&&c.pcs.A.getTransceivers()[1].sender.track===null);
    check('camera-free sharer still shows participant strip',screenLayout(wb,'A'));
    c.apps.A.stopScreen();await wait(60);
    c.apps.A.dropAllPeers();c.apps.B.dropAllPeers();
    check('leave clears camera and screen receive streams',
      Object.keys(c.apps.B.S.get('remoteStreams')).length===0&&Object.keys(c.apps.B.S.get('remoteScreenStreams')).length===0);
  }catch(e){error=e.stack;}
  finally{
    for(const f of frames)if(f.contentWindow.testApp)f.contentWindow.testApp.dropAllPeers();
    timers.forEach(clearInterval);tracks.forEach(t=>t.stop());
    await Promise.all(audioContexts.map(c=>c.close()));
    console.log('MEDIA_RESULT '+JSON.stringify({passed:!error&&checks.every(c=>c.ok),checks,error}));
  }
})();
