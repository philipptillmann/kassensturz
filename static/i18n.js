/* Translate developer-owned text before inserting any saved user data. */
window.I18n=(()=>{
 const language=localStorage.getItem('kassensturz-language')==='en'?'en':'de';
 const catalog=window.KassensturzEnglish||{};
 const keys=Object.keys(catalog).sort((a,b)=>b.length-a.length);
 const escape=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const pattern=new RegExp(keys.map(escape).join('|'),'gu');
 function t(s){if(language!=='en'||typeof s!=='string')return s;if(catalog[s])return catalog[s];return s.replace(pattern,(match,offset)=>{
  const before=s[offset-1]||'',after=s[offset+match.length]||'';
  return (/\p{L}/u.test(match[0])&&/\p{L}/u.test(before))||(/\p{L}/u.test(match.at(-1))&&/\p{L}/u.test(after))?match:catalog[match];
 });}
 function setLanguage(value){localStorage.setItem('kassensturz-language',value==='en'?'en':'de');document.cookie='kassensturz_language='+value+'; Path=/; SameSite=Lax'+(location.protocol==='https:'?'; Secure':'');location.reload();}
 document.documentElement.lang=language;
 document.title=t(document.title);
 document.cookie='kassensturz_language='+language+'; Path=/; SameSite=Lax'+(location.protocol==='https:'?'; Secure':'');
 const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);let node;
 while(node=walker.nextNode()){if(!['SCRIPT','STYLE'].includes(node.parentElement.tagName))node.nodeValue=t(node.nodeValue);}
 document.querySelectorAll('[placeholder],[title],[aria-label],[alt]').forEach(el=>['placeholder','title','aria-label','alt'].forEach(a=>{if(el.hasAttribute(a))el.setAttribute(a,t(el.getAttribute(a)));}));
 const selector=document.getElementById('language');if(selector){selector.value=language;selector.onchange=()=>setLanguage(selector.value);}
 const manual=document.getElementById('userManual');if(manual)manual.href='/manual/'+language;
 const date=value=>new Intl.DateTimeFormat(language==='en'?'en-GB':'de-DE').format(new Date(value+'T12:00:00'));
 return {date,language,locale:language==='en'?'en-GB':'de-DE',t,setLanguage,tpl:(parts,...values)=>parts.reduce((result,part,i)=>result+t(part)+(i<values.length?values[i]:''),'')};
})();
