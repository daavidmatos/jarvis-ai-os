/* JARVIS Creative Bridge for Illustrator + After Effects. ES3-compatible ExtendScript. */
var JARVIS_AI = JARVIS_AI || {};

(function(ns){
  function hostName(){
    try {
      var n=String(BridgeTalk.appName||'').toLowerCase();
      if(n.indexOf('illustrator')>=0) return 'illustrator';
      if(n.indexOf('aftereffects')>=0 || n.indexOf('after_effects')>=0) return 'after_effects';
    } catch(e) {}
    try {
      var a=String(app.name||'').toLowerCase();
      if(a.indexOf('illustrator')>=0) return 'illustrator';
      if(a.indexOf('after effects')>=0) return 'after_effects';
    } catch(e2) {}
    return 'unknown';
  }
  function esc(s){return String(s).replace(/\\/g,'\\\\').replace(/"/g,'\\"').replace(/\r/g,'\\r').replace(/\n/g,'\\n').replace(/\t/g,'\\t');}
  function json(v){
    if(v===null || v===undefined) return 'null';
    var t=typeof v;
    if(t==='string') return '"'+esc(v)+'"';
    if(t==='number') return isFinite(v)?String(v):'null';
    if(t==='boolean') return v?'true':'false';
    if(v instanceof Array){var a=[],i;for(i=0;i<v.length;i++)a.push(json(v[i]));return '['+a.join(',')+']';}
    var p=[],k;for(k in v){if(v.hasOwnProperty && !v.hasOwnProperty(k))continue;try{p.push('"'+esc(k)+'":'+json(v[k]));}catch(e){}}return '{'+p.join(',')+'}';
  }
  function parseQuery(text){
    var out={},parts=String(text||'').split('&'),i,p,k,v;
    for(i=0;i<parts.length;i++){if(!parts[i])continue;p=parts[i].split('=');k=decodeURIComponent(p.shift()||'');v=decodeURIComponent(p.join('=')||'');out[k]=v;}
    return out;
  }
  function n(args,key,def){var x=args[key]!==undefined&&args[key]!==''?Number(args[key]):def;if(isNaN(x))throw new Error(key+' precisa ser numérico');return x;}
  function s(args,key,def){var x=args[key]!==undefined?String(args[key]):String(def||'');return x;}
  function rgb(hex){var h=String(hex||'#111111').replace('#','');var value=parseInt(h,16);return [((value>>16)&255)/255,((value>>8)&255)/255,(value&255)/255];}
  function aiColor(hex){var c=rgb(hex),x=new RGBColor();x.red=Math.round(c[0]*255);x.green=Math.round(c[1]*255);x.blue=Math.round(c[2]*255);return x;}

  function aiDoc(){if(app.documents.length<1)throw new Error('Nenhum documento ativo no Illustrator.');return app.activeDocument;}
  function aiItemByName(doc,name){var i,w=String(name||'').toLowerCase();for(i=0;i<doc.pageItems.length;i++){if(String(doc.pageItems[i].name||'').toLowerCase()===w)return doc.pageItems[i];}return null;}
  function aiItemState(item){var b={name:String(item.name||''),typename:String(item.typename||'')};try{b.position=[Number(item.position[0]),Number(item.position[1])];}catch(e){}try{b.width=Number(item.width);b.height=Number(item.height);}catch(e2){}return b;}
  function aiState(){
    var out={adapter:{name:'jarvis-illustrator-cep',write:true,version:'0.2.0',actions:['inspect_document','create_document','create_rectangle','create_text','create_artboard','create_group','set_fill','move_item','create_landing_mockup','undo']},active_document:null,items:[]};
    if(app.documents.length<1)return out;var d=app.activeDocument;out.active_document={name:String(d.name||''),width:Number(d.width),height:Number(d.height),artboards:d.artboards.length};var max=Math.min(d.pageItems.length,120),i;for(i=0;i<max;i++)out.items.push(aiItemState(d.pageItems[i]));return out;
  }
  function aiRect(doc,name,x,y,w,h,fill,corner){var top=Number(doc.height)-y;var r=corner>0?doc.pathItems.roundedRectangle(top,x,w,h,corner,corner):doc.pathItems.rectangle(top,x,w,h);r.name=name||'Rectangle';r.stroked=false;r.filled=true;r.fillColor=aiColor(fill||'#111111');return r;}
  function aiText(doc,name,text,x,y,size,fill){var t=doc.textFrames.add();t.name=name||'Text';t.contents=text;t.position=[x,Number(doc.height)-y];try{t.textRange.characterAttributes.size=size||32;t.textRange.characterAttributes.fillColor=aiColor(fill||'#111111');}catch(e){}return t;}
  function aiLanding(args){
    var w=n(args,'width',1440),h=n(args,'height',3000),doc=app.documents.add(DocumentColorSpace.RGB,w,h);var accent=s(args,'accent_hex','#111111'),bg=s(args,'background_hex','#F7F3EE');
    aiRect(doc,'Background',0,0,w,h,bg,0);aiText(doc,'Brand',s(args,'product_name','Produto'),90,90,28,'#111111');
    aiText(doc,'Hero Headline',s(args,'headline','Uma nova experiência para sua rotina'),90,360,72,'#111111');aiText(doc,'Hero Subheadline',s(args,'subheadline','Produto pensado para combinar clareza, benefício e desejo.'),90,560,25,'#555555');
    aiRect(doc,'Product Placeholder',850,250,450,620,'#FFFFFF',30);aiText(doc,'Product Label',s(args,'product_name','Produto'),970,540,34,'#111111');
    aiRect(doc,'Primary CTA',90,700,260,70,accent,30);aiText(doc,'Primary CTA Label',s(args,'cta','Conhecer produto'),130,745,18,'#FFFFFF');
    aiRect(doc,'Benefits Background',0,980,w,850,'#FFFFFF',0);aiText(doc,'Benefits Heading','Por que escolher '+s(args,'product_name','este produto')+'?',90,1100,46,'#111111');
    aiRect(doc,'Benefit 01',90,1240,560,190,bg,24);aiText(doc,'Benefit 01 Label','Benefício principal',125,1330,26,'#111111');aiRect(doc,'Benefit 02',760,1240,560,190,bg,24);aiText(doc,'Benefit 02 Label','Experiência simples',795,1330,26,'#111111');
    aiRect(doc,'Benefit 03',90,1490,560,190,bg,24);aiText(doc,'Benefit 03 Label','Prova e confiança',125,1580,26,'#111111');aiRect(doc,'Benefit 04',760,1490,560,190,bg,24);aiText(doc,'Benefit 04 Label','CTA claro',795,1580,26,'#111111');
    aiRect(doc,'Final CTA Background',90,2420,1260,400,accent,36);aiText(doc,'Final CTA Heading',s(args,'headline','Experimente agora'),160,2560,46,'#FFFFFF');aiText(doc,'Final CTA Label',s(args,'cta','Comprar agora'),160,2700,20,'#FFFFFF');
    return {name:String(doc.name||''),width:w,height:h,items:doc.pageItems.length};
  }
  function aiExecute(action,args){
    if(action==='inspect_document')return aiState();
    if(action==='create_document'){var d=app.documents.add(DocumentColorSpace.RGB,n(args,'width',1440),n(args,'height',900));return {name:String(d.name||''),width:Number(d.width),height:Number(d.height)};}
    if(action==='create_landing_mockup')return aiLanding(args);
    var doc=aiDoc();
    if(action==='create_rectangle')return aiItemState(aiRect(doc,s(args,'name','Rectangle'),n(args,'x',0),n(args,'y',0),n(args,'width',100),n(args,'height',100),s(args,'fill_hex','#111111'),n(args,'corner_radius',0)));
    if(action==='create_text')return aiItemState(aiText(doc,s(args,'name','Text'),s(args,'text','Text'),n(args,'x',0),n(args,'y',0),n(args,'font_size',32),s(args,'fill_hex','#111111')));
    if(action==='create_artboard'){var x=n(args,'x',0),y=n(args,'y',0),w=n(args,'width',1440),h=n(args,'height',900);var ab=doc.artboards.add([x,Number(doc.height)-y,x+w,Number(doc.height)-y-h]);return {index:doc.artboards.length-1,name:String(ab.name||'')};}
    if(action==='create_group'){var g=doc.groupItems.add();g.name=s(args,'name','Group');return aiItemState(g);}
    if(action==='set_fill'){var item=aiItemByName(doc,s(args,'item_name',''));if(!item)throw new Error('Item não encontrado.');item.filled=true;item.fillColor=aiColor(s(args,'fill_hex','#111111'));return aiItemState(item);}
    if(action==='move_item'){var m=aiItemByName(doc,s(args,'item_name',''));if(!m)throw new Error('Item não encontrado.');m.position=[n(args,'x',0),Number(doc.height)-n(args,'y',0)];return aiItemState(m);}
    if(action==='undo'){app.undo();return {undone:true};}
    throw new Error('Ação do Illustrator não permitida: '+action);
  }

  function aeProject(){if(!app.project)app.newProject();return app.project;}
  function aeComp(name){var p=aeProject(),i;if(name){for(i=1;i<=p.numItems;i++){if(p.item(i) instanceof CompItem && String(p.item(i).name).toLowerCase()===String(name).toLowerCase())return p.item(i);}}if(p.activeItem instanceof CompItem)return p.activeItem;throw new Error('Nenhuma composição ativa.');}
  function aeLayer(comp,name){var i,w=String(name||'').toLowerCase();for(i=1;i<=comp.numLayers;i++){if(String(comp.layer(i).name||'').toLowerCase()===w)return comp.layer(i);}return null;}
  function aeLayerState(l){var o={name:String(l.name||''),index:l.index};try{o.inPoint=l.inPoint;o.outPoint=l.outPoint;o.enabled=l.enabled;}catch(e){}return o;}
  function aeState(){var p=aeProject(),out={adapter:{name:'jarvis-after-effects-cep',write:true,version:'0.2.0',actions:['inspect_project','create_composition','add_text_layer','add_solid_layer','add_shape_rectangle','set_layer_position','set_layer_scale','set_layer_opacity','add_position_keyframe','create_marketing_comp','undo']},active_document:null,compositions:[],layers:[]},i,item;if(p.activeItem instanceof CompItem){item=p.activeItem;out.active_document={name:String(item.name),width:item.width,height:item.height,duration:item.duration,fps:item.frameRate};for(i=1;i<=Math.min(item.numLayers,120);i++)out.layers.push(aeLayerState(item.layer(i)));}for(i=1;i<=p.numItems&&out.compositions.length<40;i++){item=p.item(i);if(item instanceof CompItem)out.compositions.push({name:String(item.name),width:item.width,height:item.height,duration:item.duration,fps:item.frameRate});}return out;}
  function aeText(comp,name,text,x,y,size){var l=comp.layers.addText(text);l.name=name||'Text';var prop=l.property('Source Text'),td=prop.value;try{td.fontSize=size||64;prop.setValue(td);}catch(e){}l.property('Position').setValue([x,y]);return l;}
  function aeMarketing(args){var p=aeProject(),w=Math.round(n(args,'width',1080)),h=Math.round(n(args,'height',1350)),dur=n(args,'duration',8),fps=n(args,'fps',30),comp=p.items.addComp(s(args,'name','JARVIS Marketing'),w,h,1,dur,fps);var bg=rgb(s(args,'background_hex','#111111')),accent=rgb(s(args,'accent_hex','#FFFFFF'));var b=comp.layers.addSolid(bg,'Background',w,h,1,dur);b.moveToEnd();aeText(comp,'Headline',s(args,'headline','Sua ideia, em movimento.'),w*0.08,h*0.34,Math.max(54,w*0.075));if(s(args,'subheadline',''))aeText(comp,'Subheadline',s(args,'subheadline',''),w*0.08,h*0.48,Math.max(28,w*0.035));if(s(args,'cta','')){var c=comp.layers.addSolid(accent,'CTA',Math.round(w*0.36),Math.round(h*0.09),1,dur);c.property('Position').setValue([w*0.27,h*0.66]);aeText(comp,'CTA Label',s(args,'cta','Saiba mais'),w*0.13,h*0.68,Math.max(22,w*0.027));}return {name:String(comp.name),width:w,height:h,duration:dur,fps:fps,layers:comp.numLayers};}
  function aeExecute(action,args){
    if(action==='inspect_project')return aeState();
    if(action==='create_composition'){var p=aeProject(),c=p.items.addComp(s(args,'name','Composition'),Math.round(n(args,'width',1920)),Math.round(n(args,'height',1080)),1,n(args,'duration',10),n(args,'fps',30));return {name:String(c.name),width:c.width,height:c.height,duration:c.duration,fps:c.frameRate};}
    if(action==='create_marketing_comp')return aeMarketing(args);
    var comp=aeComp(s(args,'comp_name',''));
    if(action==='add_text_layer')return aeLayerState(aeText(comp,s(args,'name','Text'),s(args,'text','Text'),n(args,'x',comp.width/2),n(args,'y',comp.height/2),n(args,'font_size',64)));
    if(action==='add_solid_layer'){var co=rgb(s(args,'fill_hex','#111111')),solid=comp.layers.addSolid(co,s(args,'name','Solid'),Math.round(n(args,'width',comp.width)),Math.round(n(args,'height',comp.height)),1,comp.duration);return aeLayerState(solid);}
    if(action==='add_shape_rectangle'){var cr=rgb(s(args,'fill_hex','#111111')),r=comp.layers.addSolid(cr,s(args,'name','Rectangle'),Math.round(n(args,'width',200)),Math.round(n(args,'height',120)),1,comp.duration);r.property('Position').setValue([n(args,'x',comp.width/2),n(args,'y',comp.height/2)]);return aeLayerState(r);}
    var layer=aeLayer(comp,s(args,'layer_name',''));if(!layer)throw new Error('Layer não encontrado.');
    if(action==='set_layer_position'){layer.property('Position').setValue([n(args,'x',0),n(args,'y',0)]);return aeLayerState(layer);}
    if(action==='set_layer_scale'){layer.property('Scale').setValue([n(args,'x',100),n(args,'y',100)]);return aeLayerState(layer);}
    if(action==='set_layer_opacity'){layer.property('Opacity').setValue(n(args,'opacity',100));return aeLayerState(layer);}
    if(action==='add_position_keyframe'){layer.property('Position').setValueAtTime(n(args,'time',0),[n(args,'x',0),n(args,'y',0)]);return aeLayerState(layer);}
    if(action==='undo'){app.undo();return {undone:true};}
    throw new Error('Ação do After Effects não permitida: '+action);
  }

  ns.snapshot=function(){try{return json(hostName()==='illustrator'?aiState():hostName()==='after_effects'?aeState():{adapter:{name:'jarvis-adobe-cep',write:false},error:'Host não suportado'});}catch(e){return json({adapter:{name:'jarvis-adobe-cep',write:false},error:String(e)});}};
  ns.execute=function(action,encoded){var args=parseQuery(encoded),h=hostName();try{app.beginUndoGroup('JARVIS '+action);}catch(e0){}try{var result=h==='illustrator'?aiExecute(action,args):h==='after_effects'?aeExecute(action,args):(function(){throw new Error('Host não suportado');})();return json({ok:true,result:result});}catch(e){return json({ok:false,error:String(e)});}finally{try{app.endUndoGroup();}catch(e2){}}};
})(JARVIS_AI);
