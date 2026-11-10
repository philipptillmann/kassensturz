const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const catalog=JSON.parse(fs.readFileSync(__dirname+'/../static/locales/en.json','utf8'));
function runtime(language){
 const source={value:language},text={nodeValue:'Einstellungen',parentElement:{tagName:'LABEL'}};
 const selector={value:''},manual={href:''};let next=text,reloaded=false;
 const document={documentElement:{},title:'Kassensturz · Anmelden',body:{},cookie:'',
 createTreeWalker:()=>({nextNode:()=>{const result=next;next=null;return result}}),querySelectorAll:()=>[],getElementById:id=>({language:selector,userManual:manual}[id])};
 const context={window:{KassensturzEnglish:catalog},localStorage:{getItem:()=>source.value,setItem:(_,value)=>source.value=value},document,NodeFilter:{SHOW_TEXT:4},location:{protocol:'https:',reload:()=>reloaded=true}};
 vm.runInNewContext(fs.readFileSync(__dirname+'/../static/i18n.js','utf8'),context);
 return {...context,api:context.window.I18n,text,selector,manual,source,reloaded:()=>reloaded};
}
const en=runtime('en');assert.equal(en.api.t('Neue Buchung'),'New entry');assert.equal(en.text.nodeValue,'Settings');assert.equal(en.document.documentElement.lang,'en');assert.equal(en.manual.href,'/manual/en');
const userText='Ausgaben · Vermögen · <img src=x>';assert.equal(en.api.tpl`Buchungen: ${userText}`,`Entries: ${userText}`);
assert.equal(en.api.t('Neuausgaben'),'Neuausgaben');assert.equal(en.api.locale,'en-GB');
en.selector.value='de';en.selector.onchange();assert.equal(en.source.value,'de');assert.equal(en.reloaded(),true);
const de=runtime('de');assert.equal(de.text.nodeValue,'Einstellungen');assert.equal(de.api.tpl`Buchungen: ${userText}`,`Buchungen: ${userText}`);assert.equal(de.api.locale,'de-DE');assert.equal(de.manual.href,'/manual/de');
console.log('Language preference, template isolation and locale checks passed.');
