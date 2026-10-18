package de.kassensturz.app

import android.app.Activity
import android.app.AlertDialog
import android.app.DatePickerDialog
import android.content.Intent
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Bundle
import android.provider.MediaStore
import android.text.Editable
import android.text.InputType
import android.text.TextWatcher
import android.view.Gravity
import android.view.View
import android.widget.*
import androidx.core.content.FileProvider
import com.google.mlkit.vision.common.InputImage
import com.google.mlkit.vision.text.TextRecognition
import com.google.mlkit.vision.text.latin.TextRecognizerOptions
import java.io.File
import java.math.BigDecimal
import java.text.NumberFormat
import java.time.LocalDate
import java.time.YearMonth
import java.time.format.DateTimeFormatter
import java.util.Locale
import java.util.concurrent.Executors

class MainActivity : Activity() {
    private val green=Color.rgb(37,79,67)
    private val ink=Color.rgb(35,45,40)
    private val muted=Color.rgb(103,112,105)
    private val pageColor=Color.rgb(245,244,239)
    private val worker=Executors.newSingleThreadExecutor()
    private lateinit var store: Store
    private var data=Snapshot(emptyList(),emptyList(),emptyList(),emptyList(),emptyList())
    private lateinit var root: LinearLayout
    private lateinit var content: LinearLayout
    private var demo=false
    private var effective=false
    private var month=YearMonth.now()
    private var tab=0
    private var busy=false
    private var initialLoad=true
    private var deferredResult: Triple<Int,Int,Intent?>?=null
    private var editor: Editor?=null
    private var cameraFile: File?=null
    private var pendingDataset: Boolean?=null
    private val currency=NumberFormat.getCurrencyInstance(Locale.GERMANY)
    private fun money(n: Long)=currency.format(BigDecimal(n).movePointLeft(2))
    private fun amountText(n: Long)=BigDecimal(n).movePointLeft(2).toPlainString().replace('.',',')
    private fun dp(n: Int)=(n*resources.displayMetrics.density).toInt()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val prefs=getPreferences(MODE_PRIVATE)
        demo=savedInstanceState?.getBoolean("demo") ?: prefs.getBoolean("demo",false)
        effective=savedInstanceState?.getBoolean("effective") ?: false
        month=runCatching { YearMonth.parse(savedInstanceState?.getString("month")) }.getOrDefault(YearMonth.now())
        tab=savedInstanceState?.getInt("tab") ?: 0
        pendingDataset=savedInstanceState?.takeIf { it.containsKey("pendingDataset") }?.getBoolean("pendingDataset")
        cameraFile=savedInstanceState?.getString("camera")?.let(::File)
        val draft=savedInstanceState?.getBundle("draft")
        store=Store(this,demo)
        screen()
        work({store.snapshot()}) { data=it;screen();initialLoad=false;if(draft!=null) edit(null,draft)
            deferredResult?.let { (code,result,intent)->deferredResult=null;onActivityResult(code,result,intent) } }
    }
    override fun onSaveInstanceState(out: Bundle) {
        super.onSaveInstanceState(out)
        out.putBoolean("demo",demo);out.putBoolean("effective",effective);out.putString("month",month.toString());out.putInt("tab",tab)
        out.putString("camera",cameraFile?.path);pendingDataset?.let { out.putBoolean("pendingDataset",it) };editor?.let { out.putBundle("draft",it.draft()) }
    }
    override fun onDestroy() { super.onDestroy(); worker.execute { store.close() };worker.shutdown() }
    private fun toast(message: String) { Toast.makeText(this,message,Toast.LENGTH_LONG).show() }
    private fun <T> work(task: ()->T, done: (T)->Unit = {}) {
        if(busy) { toast("Bitte den laufenden Vorgang abwarten.");return }
        busy=true;root.isEnabled=false
        editor?.window?.let { it.setCancelable(false);it.getButton(AlertDialog.BUTTON_POSITIVE)?.isEnabled=false;it.getButton(AlertDialog.BUTTON_NEGATIVE)?.isEnabled=false }
        worker.execute {
            val result=runCatching(task)
            runOnUiThread { busy=false;if(!isDestroyed) { root.isEnabled=true;editor?.window?.let { it.setCancelable(true);it.getButton(AlertDialog.BUTTON_POSITIVE)?.isEnabled=true;it.getButton(AlertDialog.BUTTON_NEGATIVE)?.isEnabled=true };result.fold(done) { error -> AlertDialog.Builder(this).setTitle("Vorgang fehlgeschlagen").setMessage(error.message ?: "Bitte erneut versuchen.").setPositiveButton("OK",null).show() } } }
        }
    }
    private fun change(task: ()->Unit, done: ()->Unit = {}) { work({task();store.snapshot()}) { data=it;done();screen() } }
    private fun column(parent: LinearLayout?=null)=LinearLayout(this).apply { orientation=LinearLayout.VERTICAL;parent?.addView(this,LinearLayout.LayoutParams(-1,-2)) }
    private fun row(parent: LinearLayout)=LinearLayout(this).apply { orientation=LinearLayout.HORIZONTAL;gravity=Gravity.CENTER_VERTICAL;parent.addView(this,LinearLayout.LayoutParams(-1,-2)) }
    private fun label(parent: LinearLayout, text: String, size: Float=16f, bold: Boolean=false, color: Int=ink)=TextView(this).apply {
        this.text=text;textSize=size;setTextColor(color);if(bold)setTypeface(null,Typeface.BOLD);setPadding(0,dp(6),0,dp(6));parent.addView(this)
    }
    private fun button(parent: LinearLayout, title: String, action: ()->Unit)=Button(this).apply {
        text=title;isAllCaps=false;setTextColor(green);parent.addView(this);setOnClickListener { if(!busy) action() }
    }
    private fun field(parent: LinearLayout, title: String, value: String="", numeric: Boolean=false, lines: Int=1)=EditText(this).apply {
        hint=title;contentDescription=title;setText(value);textSize=16f
        inputType=if(numeric) InputType.TYPE_CLASS_NUMBER or InputType.TYPE_NUMBER_FLAG_DECIMAL or InputType.TYPE_NUMBER_FLAG_SIGNED else InputType.TYPE_CLASS_TEXT or if(lines>1) InputType.TYPE_TEXT_FLAG_MULTI_LINE or InputType.TYPE_TEXT_FLAG_CAP_SENTENCES else InputType.TYPE_TEXT_FLAG_CAP_SENTENCES
        minLines=lines;maxLines=maxOf(lines,6);parent.addView(this,LinearLayout.LayoutParams(-1,-2))
    }
    private fun select(parent: LinearLayout, title: String, options: List<String>, chosen: String?=null): Spinner {
        label(parent,title,13f,color=muted)
        return Spinner(this).apply { adapter=ArrayAdapter(this@MainActivity,android.R.layout.simple_spinner_dropdown_item,options);parent.addView(this,LinearLayout.LayoutParams(-1,dp(48)));setSelection(options.indexOf(chosen).coerceAtLeast(0)) }
    }
    private fun box(parent: LinearLayout)=column(parent).apply {
        background=GradientDrawable().apply { setColor(Color.WHITE);cornerRadius=dp(16).toFloat() }
        setPadding(dp(16),dp(10),dp(16),dp(14));(layoutParams as LinearLayout.LayoutParams).setMargins(0,dp(8),0,dp(8))
    }
    private fun check(parent: LinearLayout,title: String,value: Boolean)=CheckBox(this).apply { text=title;isChecked=value;parent.addView(this) }
    private fun dialog(title: String, view: View, actionTitle: String="Speichern", action: ()->Unit): AlertDialog {
        val scroll=ScrollView(this).apply { addView(view) }
        return AlertDialog.Builder(this).setTitle(title).setView(scroll).setNegativeButton("Abbrechen",null).setPositiveButton(actionTitle,null).create().also { dialog ->
            dialog.setOnShowListener { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { if(!busy) try { action();dialog.dismiss() } catch(e: Exception) { toast(e.message ?: "Eingabe prüfen.") } } };dialog.show()
        }
    }
    private fun form()=column().apply { setPadding(dp(20),dp(8),dp(20),dp(12)) }
    private fun confirm(title: String,message: String,action: ()->Unit) { AlertDialog.Builder(this).setTitle(title).setMessage(message).setNegativeButton("Abbrechen",null).setPositiveButton("Bestätigen") { _,_->if(!busy)action() }.show() }
    private fun screen() {
        root=column().apply { setPadding(dp(18),0,dp(18),0);setBackgroundColor(pageColor) }
        setContentView(root)
        root.setOnApplyWindowInsetsListener { v,insets -> v.setPadding(dp(18)+insets.systemWindowInsetLeft,insets.systemWindowInsetTop,dp(18)+insets.systemWindowInsetRight,insets.systemWindowInsetBottom);insets }
        val header=row(root)
        label(header,"Kassensturz",25f,true).layoutParams=LinearLayout.LayoutParams(0,-2,1f)
        button(header,if(demo) "Demo ▾" else "Privat ▾") {
            AlertDialog.Builder(this).setTitle("Datensatz").setSingleChoiceItems(arrayOf("Privat","Demo"),if(demo)1 else 0) { d,choice ->
                d.dismiss();val next=choice==1
                if(next!=demo) work({store.close();store=Store(this,next);store.snapshot()}) { demo=next;data=it;getPreferences(MODE_PRIVATE).edit().putBoolean("demo",demo).apply();screen() }
            }.show()
        }
        val nav=row(root)
        listOf("Übersicht","Diagramme","Buchungen","Mehr").forEachIndexed { i,name -> button(nav,name) { tab=i;screen() }.apply { textSize=12f;minWidth=0;setPadding(0,0,0,0);layoutParams=LinearLayout.LayoutParams(0,dp(48),1f);if(tab==i)setTypeface(null,Typeface.BOLD) } }
        val scroll=ScrollView(this);root.addView(scroll,LinearLayout.LayoutParams(-1,0,1f));content=column();scroll.addView(content)
        if(tab!=3) {
            val period=row(content)
            button(period,"‹") { month=month.minusMonths(1);screen() }.layoutParams=LinearLayout.LayoutParams(dp(48),-2)
            button(period,month.format(DateTimeFormatter.ofPattern("MMMM yyyy",Locale.GERMAN))) {
                DatePickerDialog(this,{_,y,m,_->month=YearMonth.of(y,m+1);screen()},month.year,month.monthValue-1,1).show()
            }.layoutParams=LinearLayout.LayoutParams(0,-2,1f)
            button(period,"›") { month=month.plusMonths(1);screen() }.layoutParams=LinearLayout.LayoutParams(dp(48),-2)
            check(content,"Effektive Kosten",effective).setOnCheckedChangeListener { _,value -> effective=value;screen() }
        }
        when(tab) { 0->overview();1->graphs();2->transactions();else->settings() }
        if(tab!=3) button(root,"+ Buchung") { edit(null) }
    }
    private fun report(period: String?=month.toString())=Ledger.rows(data.entries,period,effective,data.accounts,data.transfers)
    private fun overview() {
        button(content,"Barausgabe") {
            edit(null,Bundle().apply { putString("payment","Bar");putString("type","Ausgabe") })
        }.apply {
            setCompoundDrawablesWithIntrinsicBounds(R.drawable.ic_cash,0,0,0)
            compoundDrawablePadding=dp(10)
            gravity=Gravity.CENTER_VERTICAL or Gravity.START
            setPadding(dp(16),dp(8),dp(16),dp(8))
            backgroundTintList=android.content.res.ColorStateList.valueOf(Color.rgb(231,238,230))
            layoutParams=LinearLayout.LayoutParams(-1,dp(56))
        }
        val totals=Ledger.totals(report())
        val stats=box(content)
        label(stats,"${month.format(DateTimeFormatter.ofPattern("MMMM",Locale.GERMAN))} · ${if(effective) "effektiv" else "alle Buchungen"}",14f,color=muted)
        label(stats,money(totals.net),32f,true,green);label(stats,"Ausgaben nach Erstattungen",14f,color=muted)
        label(stats,"Ausgaben ${money(totals.expenses)}   ·   Erstattungen ${money(totals.credits)}",14f)
        label(stats,"Einnahmen ${money(totals.income)}   ·   Saldo ${money(totals.balance)}",14f)
        val cats=categoryTotals()
        val card=box(content);label(card,"Nach Kategorie",20f,true)
        if(cats.isEmpty())label(card,"Noch keine Ausgaben in diesem Monat.",color=muted)
        cats.forEach { (name,value) -> label(card,"$name   ${money(value)}") }
        val recent=box(content);label(recent,"Letzte Buchungen",20f,true)
        report().take(6).forEach { entryRow(recent,it) }
        if(report().isEmpty())label(recent,"Mit + Buchung einen Eintrag anlegen.",color=muted)
    }
    private fun categoryTotals(): List<Pair<String,Long>> {
        if(effective) return report().filter { it.kind!="income" }.flatMap { r -> if(r.parts.isEmpty()) listOf(r.category to r.amount) else r.parts.map { it.category to it.amount } }.groupBy { it.first }.map { (k,v)->k to v.sumOf { it.second } }.filter { it.second!=0L }.sortedByDescending { it.second }
        return data.entries.filter { it.date.startsWith(month.toString()) && it.kind!="income" }.flatMap { e -> if(e.parts.isEmpty()) listOf(e.category to e.amount) else e.parts.map { it.category to it.amount } }.groupBy { it.first }.map { (k,v)->k to v.sumOf { it.second } }.filter { it.second!=0L }.sortedByDescending { it.second }
    }
    private fun entryRow(parent: LinearLayout,r: ReportRow) {
        val b=column(parent)
        label(b,r.name,17f,true)
        label(b,"${r.date} · ${r.category}${if(r.grouped) " · Gruppe" else ""}   ${money(r.amount)}",14f,color=if(r.amount<0)green else muted)
        b.setPadding(0,dp(6),0,dp(6));b.setOnClickListener {
            if(r.ids.size==1 && !r.grouped) data.entries.find { it.id==r.ids.first() }?.let { edit(it) }
            else { val entries=r.ids.mapNotNull { id->data.entries.find { it.id==id } };AlertDialog.Builder(this).setTitle(r.name).setItems(entries.map { "${it.date} · ${it.merchant} · ${money(it.amount)}" }.toTypedArray()) { _,i->edit(entries[i]) }.setNegativeButton("Schließen",null).show() }
        }
    }
    private fun transactions() {
        val search=field(content,"Buchungen durchsuchen")
        val list=column(content)
        fun render(query: String) { list.removeAllViews(); val rows=report().filter { r->(r.name+" "+r.category+" "+r.ids.mapNotNull { id->data.entries.find { it.id==id }?.notes }.joinToString(" ")).contains(query,true) }
            label(list,"${rows.size} Einträge",14f,color=muted);rows.take(300).forEach { entryRow(list,it) };if(rows.size>300)label(list,"Erste 300 Einträge. Suche eingrenzen.") }
        render("");search.addTextChangedListener(object:TextWatcher { override fun beforeTextChanged(s:CharSequence?,start:Int,count:Int,after:Int){};override fun onTextChanged(s:CharSequence?,start:Int,before:Int,count:Int){render(s.toString())};override fun afterTextChanged(e:Editable?){} })
    }
    private fun graphs() {
        val card=box(content);label(card,"Letzte zwölf Monate",20f,true)
        val metric=select(card,"Wert",listOf("Ausgaben nach Erstattungen","Ausgaben","Erstattungen","Einnahmen","Saldo"))
        val bars=column(card)
        fun render() {
            bars.removeAllViews()
            val values=Ledger.monthRange(month).map { m->val t=Ledger.totals(report(m));m to when(metric.selectedItemPosition){1->t.expenses;2->t.credits;3->t.income;4->t.balance;else->t.net} }
            val max=values.maxOfOrNull { kotlin.math.abs(it.second) }?.coerceAtLeast(1) ?: 1
            values.forEach { (name,value)->bar(bars,name,money(value),value,max) }
        }
        metric.onItemSelectedListener=object:AdapterView.OnItemSelectedListener {override fun onItemSelected(p:AdapterView<*>?,v:View?,position:Int,id:Long){render()};override fun onNothingSelected(p:AdapterView<*>?){} }
        render()
        val cats=box(content);label(cats,"Kategorien · $month",20f,true)
        val totals=categoryTotals();val max=totals.maxOfOrNull { kotlin.math.abs(it.second) }?.coerceAtLeast(1) ?: 1
        totals.forEach { (name,value)->bar(cats,name,money(value),value,max) }
    }
    private fun bar(parent: LinearLayout,name:String,value:String,amount:Long,max:Long) {
        label(parent,"$name   $value",14f)
        val track=FrameLayout(this);track.setBackgroundColor(Color.rgb(235,238,232));parent.addView(track,LinearLayout.LayoutParams(-1,dp(9)))
        val fill=View(this);fill.setBackgroundColor(if(amount>=0)green else Color.rgb(180,111,60));track.addView(fill,FrameLayout.LayoutParams(1,-1))
        track.post { fill.layoutParams=FrameLayout.LayoutParams((track.width*kotlin.math.abs(amount).toDouble()/max).toInt().coerceAtLeast(if(amount==0L)0 else 2),-1) }
    }
    private fun settings() {
        val cats=box(content);label(cats,"Kategorien",20f,true);label(cats,"Antippen zum Umbenennen, auch in gespeicherten Einträgen.",13f,color=muted)
        data.categories.forEach { old -> button(cats,old) { val f=form();val name=field(f,"Name",old);dialog("Kategorie umbenennen",f) { change({store.renameCategory(old,name.text.toString())}) } } }
        button(cats,"+ Kategorie") { nameDialog(true) }
        val payments=box(content);label(payments,"Zahlungsmittel",20f,true);label(payments,data.payments.joinToString(" · "));button(payments,"+ Zahlungsmittel") { nameDialog(false) }
        val accounts=box(content);label(accounts,"Eigene Konten",20f,true)
        data.accounts.forEach { a -> button(accounts,"${a.name} · ${amountText(a.share.toLong())} %") { accountDialog(a) } }
        button(accounts,"+ Eigenes Konto / Gemeinschaftskonto") { accountDialog(null) }
        label(accounts,"Anteile gelten nur bei effektiven Kosten. Einnahmen bleiben von Ausgaben getrennt.",13f,color=muted)
        val transfers=box(content);label(transfers,"Umbuchungen",20f,true)
        data.transfers.forEach { pair -> val a=data.entries.find { it.id==pair.outgoing };val b=data.entries.find { it.id==pair.incoming }
            button(transfers,"${a?.payment} → ${b?.payment} · ${money(a?.amount ?: 0)} · Aufheben") { change({store.unlink(pair)}) } }
        label(transfers,"Eindeutige Gegenbuchungen mit IBAN- oder Umbuchungshinweis werden automatisch zugeordnet. Andere Vorschläge bitte prüfen.",13f,color=muted)
        data.ignored.forEach { pair -> val a=data.entries.find { it.id==pair.outgoing };button(transfers,"Ignorierte Umbuchung ${a?.date} · ${money(a?.amount ?: 0)} erneut vorschlagen") { change({store.reconsider(pair)}) } }
        button(transfers,"Gegenbuchungen suchen") { work({store.transferCandidates()}) { candidates ->
            if(candidates.isEmpty())toast("Keine passenden Gegenbuchungen innerhalb von drei Tagen.")
            else AlertDialog.Builder(this).setTitle("Umbuchung zuordnen").setItems(candidates.take(100).map { pair ->
                val a=data.entries.first { it.id==pair.outgoing };val b=data.entries.first { it.id==pair.incoming };"${a.date} · ${a.payment} → ${b.payment}\n${a.merchant} / ${b.merchant} · ${money(a.amount)}"
            }.toTypedArray()) { _,i->confirm("Umbuchung bestätigen","Diese beiden Buchungen werden in der effektiven Ansicht ausgeblendet.") { change({store.link(candidates[i])}) } }.setNegativeButton("Abbrechen",null).show()
        } }
        val files=box(content);label(files,"Import & Sicherung",20f,true)
        button(files,"Bank-CSV importieren") { pendingDataset=demo;openDocument(104,"*/*") }
        button(files,"CSV exportieren") { pendingDataset=demo;createDocument(102,"text/csv","kassensturz-${if(demo) "demo" else "privat"}.csv") }
        button(files,"Vollständige Sicherung erstellen") { pendingDataset=demo;createDocument(101,"application/zip","kassensturz-${if(demo) "demo" else "privat"}-${LocalDate.now()}.zip") }
        button(files,"Sicherung wiederherstellen") { pendingDataset=demo;openDocument(103,"application/zip") }
        label(files,"Sicherungen enthalten den ausgewählten Datensatz einschließlich Belegen. Wiederherstellen ersetzt diesen Datensatz. CSV enthält keine Bilder.",13f,color=muted)
        val info=box(content);label(info,"Kassensturz für Android",20f,true);label(info,"Version ${packageManager.getPackageInfo(packageName,0).versionName} · Alle Daten auf diesem Gerät",14f,color=muted)
    }
    private fun nameDialog(category: Boolean) { val f=form();val name=field(f,"Name");dialog(if(category)"Kategorie anlegen" else "Zahlungsmittel anlegen",f) { val value=name.text.toString();require(value.trim().isNotEmpty()) { "Name fehlt." };change({store.addName(value,category)}) } }
    private fun accountDialog(account: Account?) {
        val f=form();val name=field(f,"Kontoname / Zahlungsmittel",account?.name ?: "")
        if(account!=null)name.isEnabled=false
        val share=field(f,"Mein Anteil in Prozent",amountText((account?.share ?: 10000).toLong()),true)
        val income=check(f,"Anteil auch auf eingehende Beträge anwenden",account?.shareIncome ?: true)
        val iban=field(f,"IBAN (optional)",account?.iban ?: "")
        dialog("Eigenes Konto",f) { val a=Account(name.text.toString().trim(),Ledger.cents(share.text.toString()).also { require(it in 0..10000) { "Anteil: 0–100 %." } }.toInt(),income.isChecked,Store.normalizeIban(iban.text.toString()));require(a.share in 0..10000) { "Anteil: 0–100 %." };change({store.configure(a)}) }
    }
    private inner class Editor(val original: Entry?, draft: Bundle? = null) {
        val base=form()
        val type=select(base,"Art",listOf("Ausgabe","Erstattung / Beitrag","Einnahme"),draft?.getString("type") ?: if(original?.kind=="income")"Einnahme" else if((original?.amount ?: 1)<0)"Erstattung / Beitrag" else "Ausgabe")
        val date=field(base,"Datum (JJJJ-MM-TT)",draft?.getString("date") ?: original?.date ?: LocalDate.now().toString()).apply {
            inputType=InputType.TYPE_CLASS_DATETIME or InputType.TYPE_DATETIME_VARIATION_DATE
            setSingleLine(true)
        }
        val merchant=field(base,"Bezeichnung",draft?.getString("merchant") ?: original?.merchant ?: "")
        val amount=field(base,"Betrag in Euro (positiv)",draft?.getString("amount") ?: original?.let { amountText(kotlin.math.abs(it.amount)) } ?: "",true)
        val category=select(base,"Kategorie",data.categories,draft?.getString("category") ?: original?.category ?: "Unkategorisiert")
        val payment=select(base,"Zahlungsmittel",(listOf("")+data.payments+"Bar").distinct(),draft?.getString("payment") ?: original?.payment)
        val group=field(base,"Gruppe (optional)",draft?.getString("group") ?: original?.group ?: "")
        val notes=field(base,"Notizen",draft?.getString("notes") ?: original?.notes ?: "",lines=3)
        val parts=mutableListOf<Part>().apply { addAll(original?.parts ?: emptyList()) }
        val partsBox=column(base)
        val receiptLabel=label(base,"")
        var photo: File?=draft?.getString("photo")?.let(::File)
        var removeReceipt=draft?.getBoolean("removeReceipt") ?: false
        var window: AlertDialog?=null
        init {
            draft?.getString("parts")?.let { raw -> parts.clear();val a=org.json.JSONArray(raw);for(i in 0 until a.length()) { val p=a.getJSONObject(i);parts.add(Part(p.getString("name"),p.getLong("amount"),p.getString("category"),if(p.isNull("group"))null else p.getString("group"))) } }
            button(base,"+ Position aufteilen") { partDialog(null) }
            button(base,"Belegfoto auswählen (auch HEIC)") { openDocument(110,"image/*") }
            button(base,"Beleg fotografieren") { capture() }
            button(base,"Beleg anzeigen") { showReceipt() }
            button(base,"Text aus Beleg lesen") { ocr() }
            button(base,"Beleg entfernen") { photo?.delete();photo=null;removeReceipt=true;renderParts() }
            if(original!=null)button(base,"Buchung löschen") { confirm("Buchung löschen?","Der gespeicherte Beleg wird ebenfalls gelöscht.") { change({store.delete(original.id)}) { window?.dismiss();editor=null } } }
            renderParts()
        }
        fun renderParts() {
            partsBox.removeAllViews();label(partsBox,"Positionen · Summe ${money(parts.sumOf { it.amount })}",15f,true)
            parts.forEachIndexed { i,p -> button(partsBox,"${p.name} · ${money(p.amount)}\n${p.category} · ${p.group ?: "Gruppe erben"}") { partDialog(i) } }
            receiptLabel.text=if(photo!=null)"Neues Belegfoto bereit" else if(original?.receipt==true && !removeReceipt) "Beleg gespeichert" else "Kein Belegfoto"
        }
        fun partDialog(index: Int?) {
            val old=index?.let { parts[it] };val f=form();val name=field(f,"Position",old?.name ?: "");val value=field(f,"Betrag (Vorzeichen wie Buchung)",old?.let { amountText(it.amount) } ?: "",true)
            button(f,"+/− Vorzeichen wechseln") {
                val raw=value.text.toString().trim().removePrefix("+")
                val signed=if(raw.startsWith("-")) raw.removePrefix("-") else "-"+raw
                value.setText(signed);value.setSelection(signed.length);value.requestFocus()
            }
            val cat=select(f,"Kategorie",data.categories,old?.category ?: category.selectedItem?.toString())
            val mode=select(f,"Gruppenzuordnung",listOf("Gruppe der Buchung erben","Keine Gruppe","Eigene Gruppe"),when { old?.group==null->"Gruppe der Buchung erben";old.group.isEmpty()->"Keine Gruppe";else->"Eigene Gruppe" })
            val g=field(f,"Eigener Gruppenname",old?.group ?: "")
            val d=dialog("Position",f) {
                val part=Part(name.text.toString().trim(),Ledger.cents(value.text.toString()),cat.selectedItem.toString(),when(mode.selectedItemPosition){0->null;1->"";else->g.text.toString().trim().also { require(it.isNotEmpty()) { "Gruppenname fehlt." } }})
                require(part.name.isNotEmpty()) { "Positionsname fehlt." }
                if(index==null)parts.add(part) else parts[index]=part
                renderParts()
            }
            if(index!=null)button(f,"Position entfernen") { parts.removeAt(index);renderParts();d.dismiss() }
        }
        fun entry(): Entry {
            val value=Ledger.cents(amount.text.toString());require(value>0) { "Einen positiven Betrag eingeben; Art bestimmt das Vorzeichen." }
            return Entry(id=original?.id ?: 0,date=LocalDate.parse(date.text.toString().trim()).toString(),merchant=merchant.text.toString().trim(),amount=if(type.selectedItemPosition==0)value else -value,category=category.selectedItem.toString(),payment=payment.selectedItem.toString(),kind=if(type.selectedItemPosition==2)"income" else "expense",notes=notes.text.toString(),group=group.text.toString().trim(),parts=parts.toList(),counterparty=original?.counterparty ?: "",importKey=original?.importKey).also { Ledger.validate(it) }
        }
        fun draft() = Bundle().apply {
            putLong("id",original?.id ?: 0);putString("type",type.selectedItem.toString());putString("date",date.text.toString());putString("merchant",merchant.text.toString());putString("amount",amount.text.toString());putString("category",category.selectedItem?.toString());putString("payment",payment.selectedItem?.toString());putString("group",group.text.toString());putString("notes",notes.text.toString());putString("photo",photo?.path);putBoolean("removeReceipt",removeReceipt)
            putString("parts",org.json.JSONArray().apply { parts.forEach { p->put(org.json.JSONObject().put("name",p.name).put("amount",p.amount).put("category",p.category).put("group",p.group ?: org.json.JSONObject.NULL)) } }.toString())
        }
        fun showReceipt() { work({photo?.takeIf { it.exists() }?.readBytes() ?: if(!removeReceipt) original?.let { store.receipt(it.id) } else null}) { bytes ->
            if(bytes==null)toast("Kein Beleg vorhanden.") else { val image=ImageView(this@MainActivity);image.adjustViewBounds=true;image.setImageBitmap(android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.size));val scroll=ScrollView(this@MainActivity);scroll.addView(image);AlertDialog.Builder(this@MainActivity).setTitle("Beleg").setView(scroll).setPositiveButton("Schließen",null).show() }
        } }
        fun ocr() { work({photo?.readBytes() ?: if(!removeReceipt) original?.let { store.receipt(it.id) } else null}) { bytes ->
            if(bytes==null) { toast("Zuerst ein Belegfoto auswählen.");return@work }
            val bitmap=android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.size)
            val recognizer=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            busy=true
            recognizer.process(InputImage.fromBitmap(bitmap,0)).addOnSuccessListener { text ->
                if(!isDestroyed && editor===this@Editor) {
                    val f=form();val result=field(f,"Erkannter Text – bitte prüfen",text.text,lines=6)
                    val total=Regex("(?im)(?:summe|gesamt|total)[^\\n]*?([0-9]+[,.][0-9]{2})").find(text.text)?.groupValues?.get(1)
                    val choice=check(f,"Erkannten Gesamtbetrag übernehmen${total?.let { " ($it €)" } ?: " (nicht gefunden)"}",false);choice.isEnabled=total!=null
                    dialog("Belegtext",f,"Übernehmen") { notes.setText((notes.text.toString()+"\n"+result.text.toString()).trim());if(choice.isChecked && total!=null)amount.setText(total) }
                }
            }.addOnFailureListener { if(!isDestroyed)toast("Texterkennung fehlgeschlagen: ${it.message}") }.addOnCompleteListener { busy=false;bitmap.recycle();recognizer.close() }
        } }
    }
    private fun edit(original: Entry?, draft: Bundle?=null) {
        if(busy)return
        val restored=original ?: draft?.getLong("id")?.takeIf { it>0 }?.let { id->data.entries.find { it.id==id } }
        val e=Editor(restored,draft);editor=e
        val scroll=ScrollView(this).apply { addView(e.base) }
        val window=AlertDialog.Builder(this).setTitle(if(restored!=null)"Buchung bearbeiten" else if(e.payment.selectedItem=="Bar")"Neue Barausgabe" else "Neue Buchung").setView(scroll).setNegativeButton("Abbrechen",null).setPositiveButton("Speichern",null).create()
        e.window=window
        window.setOnShowListener { window.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { if(!busy)try { val entry=e.entry();val file=e.photo
            work({store.save(entry,file?.readBytes(),e.removeReceipt);store.snapshot()}) { data=it;file?.delete();editor=null;window.dismiss();screen() }
        } catch(ex:Exception){toast(ex.message ?: "Eingaben prüfen.")} } }
        window.setOnCancelListener { if(busy)toast("Vorgang läuft.") }
        window.setOnDismissListener { if(editor===e)editor=null }
        window.show();window.window?.setLayout(-1,-1)
    }
    private fun createDocument(code:Int,mime:String,name:String) { startActivityForResult(Intent(Intent.ACTION_CREATE_DOCUMENT).apply { addCategory(Intent.CATEGORY_OPENABLE);type=mime;putExtra(Intent.EXTRA_TITLE,name) },code) }
    private fun openDocument(code:Int,mime:String) { startActivityForResult(Intent(Intent.ACTION_OPEN_DOCUMENT).apply { addCategory(Intent.CATEGORY_OPENABLE);type=mime },code) }
    private fun capture() {
        try {
            val folder=File(cacheDir,"camera").apply { mkdirs() }
            cameraFile=File.createTempFile("capture-",".jpg",folder)
            val uri=FileProvider.getUriForFile(this,"de.kassensturz.app.files",cameraFile!!)
            startActivityForResult(Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply { putExtra(MediaStore.EXTRA_OUTPUT,uri);addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION);clipData=android.content.ClipData.newRawUri("Beleg",uri) },111)
        } catch(e:Exception) { toast("Kamera nicht verfügbar: ${e.message}") }
    }
    override fun onActivityResult(requestCode:Int,resultCode:Int,result:Intent?) {
        super.onActivityResult(requestCode,resultCode,result)
        if(initialLoad) { deferredResult=Triple(requestCode,resultCode,result);return }
        if(resultCode!=RESULT_OK)return
        val uri=if(requestCode==111)cameraFile?.let(Uri::fromFile) else result?.data
        if(uri==null)return
        if(requestCode in 101..104 && pendingDataset!=null && pendingDataset!=demo) { toast("Datensatz wurde gewechselt. Vorgang bitte erneut starten.");return }
        when(requestCode) {
            101 -> work({ contentResolver.openOutputStream(uri,"wt")?.use { store.backup(it) } ?: error("Zieldatei konnte nicht geöffnet werden.") }) { toast("Sicherung erstellt.") }
            102 -> work({ contentResolver.openOutputStream(uri,"wt")?.bufferedWriter(Charsets.UTF_8)?.use { it.write(BankCsv.export(store.snapshot().entries)) } ?: error("Zieldatei konnte nicht geöffnet werden.") }) { toast("CSV exportiert.") }
            103 -> confirm("${if(demo)"Demo" else "Privat"} ersetzen?","Die Sicherung ersetzt alle Buchungen, Einstellungen und Belege dieses Datensatzes. Vorher eine eigene Sicherung erstellen.") {
                change({contentResolver.openInputStream(uri)?.use { store.restore(it) } ?: error("Datei konnte nicht geöffnet werden.")}) { toast("Sicherung wiederhergestellt.") }
            }
            104 -> work({contentResolver.openInputStream(uri)?.use { Store.readLimited(it,8_000_000) } ?: error("CSV konnte nicht geöffnet werden.")}) { bytes ->
                val utf8=Charsets.UTF_8.newDecoder().onMalformedInput(java.nio.charset.CodingErrorAction.REPORT)
                val text=runCatching { utf8.decode(java.nio.ByteBuffer.wrap(bytes)).toString() }.getOrElse { bytes.toString(charset("windows-1252")) }
                importCsv(text)
            }
            110,111 -> { val target=editor ?: return
                work({val jpeg=ReceiptImages.jpeg(this,uri);File.createTempFile("receipt-",".jpg",cacheDir).apply { writeBytes(jpeg) }}) { file ->
                    if(editor===target) { target.photo?.delete();target.photo=file;target.removeReceipt=false;target.renderParts() } else file.delete()
                    if(requestCode==111) { cameraFile?.delete();cameraFile=null }
                }
            }
        }
    }
    private fun importCsv(text:String) {
        val f=form();val delimiter=select(f,"Trennzeichen",listOf("Semikolon (;)","Komma (,)","Tabulator"))
        val account=field(f,"Konto / Zahlungsmittel")
        val cat=select(f,"Kategorie für importierte Buchungen",data.categories,"Unkategorisiert")
        val signs=check(f,"Bank-Vorzeichen: Abbuchungen negativ",true)
        val income=check(f,"Alle Gutschriften als Einnahmen (statt Erstattungen)",false)
        label(f,"Erste Zeile muss Spaltennamen enthalten. Im nächsten Schritt Spalten zuordnen und Vorschau prüfen.",14f,color=muted)
        dialog("Bank-CSV",f,"Spalten zuordnen") {
            val rows=BankCsv.parse(text,when(delimiter.selectedItemPosition){1->',';2->'\t';else->';'})
            require(rows.size>1) { "Keine CSV-Daten gefunden." };require(account.text.isNotBlank()) { "Konto fehlt." }
            val mapping=form();val headers=rows.first().mapIndexed { i,h->"${i+1}: $h" }
            fun guess(vararg words:String)=headers.firstOrNull { h->words.any { h.contains(it,true) } }
            val date=select(mapping,"Buchungsdatum",headers,guess("Buchungstag","Datum","Date"))
            val merchant=select(mapping,"Bezeichnung / Verwendungszweck",headers,guess("Verwendungszweck","Buchungstext","Beschreibung","Merchant"))
            val amount=select(mapping,"Betrag",headers,guess("Betrag","Amount"))
            val iban=select(mapping,"Gegenkonto-IBAN (optional)",listOf("Keine")+headers)
            dialog("Spalten zuordnen",mapping,"Vorschau") {
                val entries=BankCsv.entries(rows,date.selectedItemPosition,merchant.selectedItemPosition,amount.selectedItemPosition,account.text.toString(),cat.selectedItem.toString(),signs.isChecked,iban.selectedItemPosition-1,income.isChecked)
                require(entries.isNotEmpty()) { "Keine Buchungen mit Betrag gefunden." }
                work({store.previewImport(entries)}) { counts ->
                    confirm("${counts.first} neue Buchungen importieren?", "${counts.second} bereits vorhandene werden übersprungen.\n\n"+entries.take(8).joinToString("\n") { "${it.date} · ${it.merchant} · ${money(it.amount)}" }+"\n\nDie Prüfung wird beim Speichern wiederholt. Gutschriften können anschließend als Einnahme oder Erstattung bearbeitet werden.") {
                        work({val actual=store.importEntries(entries);actual to store.snapshot()}) { (actual,snapshot)->data=snapshot;screen();toast("${actual.first} importiert, ${actual.second} bereits vorhanden.") }
                    }
                }
            }
        }
    }
}
