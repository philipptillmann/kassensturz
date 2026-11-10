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
import org.json.JSONObject
import org.json.JSONArray

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
    private val currency get()=NumberFormat.getCurrencyInstance(L10n.locale).apply { currency=java.util.Currency.getInstance("EUR") }
    private fun money(n: Long)=currency.format(BigDecimal(n).movePointLeft(2))
    private fun amountText(n: Long)=BigDecimal(n).movePointLeft(2).toPlainString().let { if(L10n.language=="en") it else it.replace('.',',') }
    private fun dp(n: Int)=(n*resources.displayMetrics.density).toInt()

    override fun attachBaseContext(base: android.content.Context) {
        val code=base.getSharedPreferences("language",MODE_PRIVATE).getString("value","de")
        val config=android.content.res.Configuration(base.resources.configuration)
        config.setLocale(if(code=="en") Locale.UK else Locale.GERMANY)
        super.attachBaseContext(base.createConfigurationContext(config))
    }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        L10n.init(this)
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
        if(busy) { toast(L10n.t("Bitte den laufenden Vorgang abwarten."));return }
        busy=true;root.isEnabled=false
        editor?.window?.let { it.setCancelable(false);it.getButton(AlertDialog.BUTTON_POSITIVE)?.isEnabled=false;it.getButton(AlertDialog.BUTTON_NEGATIVE)?.isEnabled=false }
        worker.execute {
            val result=runCatching(task)
            runOnUiThread { busy=false;if(!isDestroyed) { root.isEnabled=true;editor?.window?.let { it.setCancelable(true);it.getButton(AlertDialog.BUTTON_POSITIVE)?.isEnabled=true;it.getButton(AlertDialog.BUTTON_NEGATIVE)?.isEnabled=true };result.fold(done) { error -> AlertDialog.Builder(this).setTitle(L10n.t("Vorgang fehlgeschlagen")).setMessage(error.message ?: L10n.t("Bitte erneut versuchen.")).setPositiveButton("OK",null).show() } } }
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
    private fun dialog(title: String, view: View, actionTitle: String=L10n.t("Speichern"), action: ()->Unit): AlertDialog {
        val scroll=ScrollView(this).apply { addView(view) }
        return AlertDialog.Builder(this).setTitle(title).setView(scroll).setNegativeButton(L10n.t("Abbrechen"),null).setPositiveButton(actionTitle,null).create().also { dialog ->
            dialog.setOnShowListener { dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { if(!busy) try { action();dialog.dismiss() } catch(e: Exception) { toast(e.message ?: L10n.t("Eingabe prüfen.")) } } };dialog.show()
        }
    }
    private fun form()=column().apply { setPadding(dp(20),dp(8),dp(20),dp(12)) }
    private fun confirm(title: String,message: String,action: ()->Unit) { AlertDialog.Builder(this).setTitle(title).setMessage(message).setNegativeButton(L10n.t("Abbrechen"),null).setPositiveButton(L10n.t("Bestätigen")) { _,_->if(!busy)action() }.show() }
    private fun screen() {
        root=column().apply { setPadding(dp(18),0,dp(18),0);setBackgroundColor(pageColor) }
        setContentView(root)
        root.setOnApplyWindowInsetsListener { v,insets -> v.setPadding(dp(18)+insets.systemWindowInsetLeft,insets.systemWindowInsetTop,dp(18)+insets.systemWindowInsetRight,insets.systemWindowInsetBottom);insets }
        val header=row(root)
        label(header,"Kassensturz",25f,true).layoutParams=LinearLayout.LayoutParams(0,-2,1f)
        button(header,if(demo) L10n.t("Demo ▾") else L10n.t("Privat ▾")) {
            AlertDialog.Builder(this).setTitle(L10n.t("Datensatz")).setSingleChoiceItems(arrayOf(L10n.t("Privat"),"Demo"),if(demo)1 else 0) { d,choice ->
                d.dismiss();val next=choice==1
                if(next!=demo) work({store.close();store=Store(this,next);store.snapshot()}) { demo=next;data=it;getPreferences(MODE_PRIVATE).edit().putBoolean("demo",demo).apply();screen() }
            }.show()
        }
        val nav=row(root)
        listOf(L10n.t("Übersicht"),L10n.t("Diagramme"),L10n.t("Buchungen"),L10n.t("Vermögen"),L10n.t("Mehr")).forEachIndexed { i,name -> button(nav,name) { tab=i;screen() }.apply { textSize=11f;minWidth=0;setPadding(0,0,0,0);layoutParams=LinearLayout.LayoutParams(0,dp(48),1f);if(tab==i)setTypeface(null,Typeface.BOLD) } }
        val scroll=ScrollView(this);root.addView(scroll,LinearLayout.LayoutParams(-1,0,1f));content=column();scroll.addView(content)
        if(tab<3) {
            val period=row(content)
            button(period,"‹") { month=month.minusMonths(1);screen() }.layoutParams=LinearLayout.LayoutParams(dp(48),-2)
            button(period,month.format(DateTimeFormatter.ofPattern("MMMM yyyy",L10n.locale))) {
                DatePickerDialog(this,{_,y,m,_->month=YearMonth.of(y,m+1);screen()},month.year,month.monthValue-1,1).show()
            }.layoutParams=LinearLayout.LayoutParams(0,-2,1f)
            button(period,"›") { month=month.plusMonths(1);screen() }.layoutParams=LinearLayout.LayoutParams(dp(48),-2)
            check(content,L10n.t("Effektive Kosten"),effective).setOnCheckedChangeListener { _,value -> effective=value;screen() }
        }
        when(tab) { 0->overview();1->graphs();2->transactions();3->wealthScreen();else->settings() }
        if(tab<3) button(root,L10n.t("+ Buchung")) { edit(null) }
    }
    private fun wealthScreen() {
        val doc=data.wealth;val summary=box(content)
        label(summary,L10n.t("Vermögensübersicht"),22f,true);label(summary,money(Wealth.total(doc)),30f,true,green)
        label(summary,("" + L10n.t("Erfasste Bestände in EUR · ") + (LocalDate.now()) + L10n.t(". Giroguthaben separat erfassen; die Buchungsliste ist kein Kontostand. Umbuchungen sind keine Ausgaben oder Einnahmen.")),14f,color=muted)
        button(summary,L10n.t("Vermögenswert anlegen")) { wealthAssetDialog() }
        button(summary,L10n.t("Bewegung erfassen")) { wealthEventDialog() }
        button(summary,L10n.t("Dauerauftrag anlegen")) { wealthPlanDialog() }
        button(summary,L10n.t("Fällige Daueraufträge buchen")) {
            val booked=Wealth.events(doc).map { it.num("plan") to it.getString("date") }.toSet()
            val due=Wealth.plans(doc).filter { it.getBoolean("enabled") }.flatMap { p -> Wealth.dates(p,"0001-01-01",LocalDate.now().toString()).filter { (p.num("id") to it) !in booked }.map { ("" + (it) + L10n.t(" · ") + (p.getString("name")) + L10n.t(" · ") + (money(p.num("amount")))) } }
            confirm(("" + (due.size) + L10n.t(" fällige Termine buchen?")),due.take(30).joinToString("\n")+L10n.t("\nBei unzureichendem Quellguthaben wird nichts gebucht. Bereits gebuchte Termine werden nicht wiederholt. Importierte Bankbuchungen anschließend im Vermögensjournal zuordnen.")) {
                change({store.wealthCommand(JSONObject().put("op","run-plans"))})
            }
        }
        Wealth.assets(doc).forEach { a ->
            val card=box(content);label(card,a.getString("name"),20f,true)
            label(card,("" + (Wealth.types[a.getString("type")]) + L10n.t(" · ") + (Wealth.decimal(a.num("rate_bp"))) + L10n.t(" % p. a."))+(a.getString("maturity").takeIf { it.isNotEmpty() }?.let { ("" + L10n.t(" · bis ") + (it)) } ?: ""),14f)
            label(card,money(Wealth.cash(doc,a)+Wealth.holdings(a)),24f,true,green)
            label(card,("" + L10n.t("Guthaben ") + (money(Wealth.cash(doc,a))) + L10n.t(" · Positionen ") + (money(Wealth.holdings(a)))),14f)
            label(card,("" + L10n.t("Letzter Bestandswert: ") + (a.getJSONArray("snapshots").rows().maxOf { it.getString("date") })),13f,color=muted)
            button(card,L10n.t("Produkt / Bestandswert bearbeiten")) { wealthAssetDialog(a) }
            button(card,L10n.t("Anlage entfernen")) { confirm(L10n.t("Anlage entfernen?"),L10n.t("Nur ohne Bewegungen oder Daueraufträge möglich.")) { change({store.wealthCommand(JSONObject().put("op","delete-asset").put("id",a.num("id")))}) } }
            if(a.getString("type")=="brokerage") {
                button(card,L10n.t("Wertpapierbestand erfassen")) { wealthPositionDialog(a) }
                button(card,L10n.t("Wertpapier kaufen / verkaufen")) { wealthPositionDialog(a,null,true) }
                a.getJSONArray("positions").rows().forEach { p ->
                    label(card,("" + (p.getString("name")) + L10n.t(" · ") + (Wealth.decimal(p.num("units"),6)) + L10n.t(" Stück × ") + (Wealth.decimal(p.num("price"),6)) + L10n.t(" EUR\nKursdatum ") + (p.getString("date")) + L10n.t(" · ") + (p.getString("symbol"))),14f)
                    button(card,("" + (p.getString("name")) + L10n.t(": Bestand / Kurs"))) { wealthPositionDialog(a,p) }
                    button(card,("" + (p.getString("name")) + L10n.t(": Handeln"))) { wealthPositionDialog(a,p,true) }
                    if(p.getString("symbol").isNotEmpty()) button(card,("" + (p.getString("name")) + L10n.t(": Kurs aktualisieren"))) { wealthQuoteDialog(a,p) }
                    if(p.num("units")==0L) button(card,L10n.t("Leere Position entfernen")) { change({store.wealthCommand(JSONObject().put("op","delete-position").put("id",a.num("id")).put("name",p.getString("name")))}) }
                }
            }
        }
        val plans=box(content);label(plans,L10n.t("Daueraufträge"),20f,true)
        Wealth.plans(doc).forEach { p -> button(plans,("" + (p.getString("name")) + L10n.t(" · ") + (money(p.num("amount"))) + L10n.t(" · ") + (if(p.getBoolean("enabled")) L10n.t("aktiv") else L10n.t("pausiert")))) { wealthPlanDialog(p) } }
        val projection=box(content);label(projection,L10n.t("Mögliche Wertentwicklung"),20f,true)
        val years=select(projection,L10n.t("Zeitraum"),listOf(L10n.t("1 Jahr"),L10n.t("5 Jahre"),L10n.t("10 Jahre"),L10n.t("20 Jahre"),L10n.t("30 Jahre")),L10n.t("10 Jahre"))
        label(projection,L10n.t("Modellrechnung: Jahresrate nominal, tagweise ACT/365, Gutschrift zum Monatsende. Depot-Szenarien ±2 Prozentpunkte. Ohne Steuern, Inflation, automatische Dividenden oder künftige Gehaltseingänge. Nach Laufzeitende unverzinst. Interne Umbuchungen erhöhen das Gesamtvermögen nicht."),14f,color=muted)
        button(projection,L10n.t("Prognose berechnen")) {
            val months=listOf(12,60,120,240,360)[years.selectedItemPosition]
            work({listOf(-200,0,200).map { Wealth.forecast(doc,months,it) }}) { results ->
                val f=form()
                listOf(L10n.t("Vorsichtig"),L10n.t("Annahme"),L10n.t("Optimistisch")).forEachIndexed { i,title ->
                    val result=results[i];label(f,title,20f,true);label(f,money(result.points.last().total),24f,true,green)
                    label(f,("" + L10n.t("Modellierter Ertrag ") + (money(result.points.last().growth)) + L10n.t(" · ") + (result.skipped) + L10n.t(" Termine mangels Guthaben ausgelassen")),14f)
                    result.points.filterIndexed { index,_ -> index==0 || index%12==0 || index==result.points.lastIndex }.forEach { label(f,("" + (it.date) + L10n.t(": ") + (money(it.total))),14f) }
                }
                AlertDialog.Builder(this).setTitle(L10n.t("Vermögensprognose")).setView(ScrollView(this).apply { addView(f) }).setPositiveButton(L10n.t("Schließen"),null).show()
            }
        }
        val journal=box(content);label(journal,L10n.t("Vermögensjournal"),20f,true)
        Wealth.events(doc).reversed().forEach { e ->
            val kinds=mapOf("transfer" to L10n.t("Umbuchung"),"interest" to L10n.t("Zinsen"),"dividend" to L10n.t("Dividende"),"fee" to L10n.t("Gebühr"),"buy" to L10n.t("Kauf"),"sell" to L10n.t("Verkauf"))
            val from=Wealth.asset(doc,e.num("from"))?.getString("name") ?: ""
            val to=Wealth.asset(doc,e.num("to"))?.getString("name") ?: ""
            label(journal,("" + (e.getString("date")) + L10n.t(" · ") + (kinds[e.getString("kind")]) + L10n.t(" · ") + (money(e.num("amount"))) + L10n.t("\n") + (from) + L10n.t(" → ") + (to) + L10n.t("\n") + (e.getString("note"))),14f)
            if(e.getString("kind")=="transfer") button(journal,L10n.t("Bankbuchungen zuordnen / lösen")) { wealthLinkDialog(e) }
        }
    }
    private fun wealthAssetDialog(a:JSONObject?=null) {
        val f=form();val name=field(f,"Name",a?.getString("name") ?: "")
        val keys=Wealth.types.keys.toList();val type=select(f,L10n.t("Produkt"),Wealth.types.values.toList(),Wealth.types[a?.getString("type") ?: "savings"])
        val date=field(f,L10n.t("Bestandsdatum JJJJ-MM-TT"),LocalDate.now().toString())
        val value=field(f,L10n.t("Bestand EUR / Depot-Verrechnungsguthaben ohne Positionen"),Wealth.decimal(a?.let { Wealth.cash(data.wealth,it) } ?: 0),true)
        val rate=field(f,L10n.t("Jahreszins / Depot-Renditeannahme %"),Wealth.decimal(a?.num("rate_bp") ?: 0),true)
        val maturity=field(f,L10n.t("Laufzeitende JJJJ-MM-TT (optional)"),a?.getString("maturity") ?: "")
        label(f,L10n.t("Nur EUR. Depotpositionen zählen zusätzlich zum Guthaben. Ein Bestandswert enthält bereits alle bis dahin erfassten Bewegungen desselben Tages. Bausparen ohne Darlehen, Bonus oder Steuern."),14f,color=muted)
        dialog(L10n.t("Vermögenswert"),f) {
            val c=JSONObject().put("op","asset").put("id",a?.num("id") ?: 0).put("name",name.text.toString()).put("type",keys[type.selectedItemPosition]).put("date",date.text.toString().trim()).put("value",Wealth.scaled(value.text.toString())).put("rate_bp",Wealth.scaled(rate.text.toString())).put("maturity",maturity.text.toString().trim())
            Wealth.apply(data.wealth,c);change({store.wealthCommand(c)})
        }
    }
    private fun wealthPlanDialog(p:JSONObject?=null) {
        val assets=Wealth.assets(data.wealth);if(assets.size<2){toast(L10n.t("Zuerst Quellkonto und Zielanlage erfassen."));return}
        val f=form();val name=field(f,L10n.t("Bezeichnung"),p?.getString("name") ?: "")
        val names=assets.map { it.getString("name") };val from=select(f,L10n.t("Von"),names,assets.find { it.num("id")==p?.num("from") }?.getString("name"));val to=select(f,L10n.t("Nach"),names,assets.find { it.num("id")==p?.num("to") }?.getString("name") ?: names[1])
        val amount=field(f,L10n.t("Betrag EUR"),p?.let { Wealth.decimal(it.num("amount")) } ?: "",true)
        val start=field(f,L10n.t("Erster Termin JJJJ-MM-TT"),p?.getString("start") ?: LocalDate.now().toString());val end=field(f,L10n.t("Letzter Termin (optional)"),p?.getString("end") ?: "")
        val rhythms=listOf(1,3,6,12);val every=select(f,L10n.t("Rhythmus"),listOf(L10n.t("Monatlich"),L10n.t("Vierteljährlich"),L10n.t("Halbjährlich"),L10n.t("Jährlich")),listOf(L10n.t("Monatlich"),L10n.t("Vierteljährlich"),L10n.t("Halbjährlich"),L10n.t("Jährlich"))[rhythms.indexOf(p?.optInt("every",1) ?: 1).coerceAtLeast(0)])
        val active=check(f,L10n.t("Aktiv"),p?.getBoolean("enabled") ?: true)
        label(f,L10n.t("Fällige Termine erst nach Bestätigung buchen. Monatsende wird gekürzt. Depotzuflüsse bleiben Verrechnungsguthaben, bis ein Kauf erfasst wird."),14f,color=muted)
        dialog(L10n.t("Vermögensdauerauftrag"),f) {
            val c=JSONObject().put("op","plan").put("id",p?.num("id") ?: 0).put("name",name.text.toString()).put("from",assets[from.selectedItemPosition].num("id")).put("to",assets[to.selectedItemPosition].num("id")).put("amount",Wealth.scaled(amount.text.toString())).put("start",start.text.toString().trim()).put("end",end.text.toString().trim()).put("every",rhythms[every.selectedItemPosition]).put("enabled",active.isChecked)
            Wealth.apply(data.wealth,c);change({store.wealthCommand(c)})
        }
    }
    private fun wealthEventDialog() {
        val assets=Wealth.assets(data.wealth);if(assets.isEmpty()){toast(L10n.t("Zuerst Vermögenswerte erfassen."));return}
        val f=form();val kinds=listOf("transfer","interest","dividend","fee");val kind=select(f,L10n.t("Art"),listOf(L10n.t("Umbuchung"),L10n.t("Zinsen"),L10n.t("Dividende"),L10n.t("Gebühr")))
        val names=assets.map { it.getString("name") };val from=select(f,L10n.t("Quelle (nur Umbuchung)"),names);val to=select(f,L10n.t("Ziel / betroffenes Produkt"),names,names.getOrNull(1))
        val amount=field(f,L10n.t("Betrag EUR"),"",true);val date=field(f,L10n.t("Datum JJJJ-MM-TT"),LocalDate.now().toString());val note=field(f,L10n.t("Notiz"))
        label(f,L10n.t("Keine Ausgabe / Einnahme. Bewegungen bleiben im Vermögensjournal; Korrekturen über Gegenumbuchung oder Bestandswert. Importierte Bankbuchungen nach dem Buchen zuordnen."),14f,color=muted)
        dialog(L10n.t("Vermögensbewegung"),f) {
            val c=JSONObject().put("op","event").put("kind",kinds[kind.selectedItemPosition]).put("from",if(kind.selectedItemPosition==0)assets[from.selectedItemPosition].num("id") else 0).put("to",assets[to.selectedItemPosition].num("id")).put("amount",Wealth.scaled(amount.text.toString())).put("date",date.text.toString().trim()).put("note",note.text.toString()).put("entries",JSONArray())
            Wealth.apply(data.wealth,c);change({store.wealthCommand(c)})
        }
    }
    private fun wealthPositionDialog(a:JSONObject,p:JSONObject?=null,trade:Boolean=false) {
        val f=form();val name=field(f,L10n.t("Positionsname (eindeutig)"),p?.getString("name") ?: "").apply { if(p!=null)isEnabled=false };val symbol=field(f,L10n.t("Börsensymbol (EUR-Notierung, optional)"),p?.getString("symbol") ?: "")
        val units=field(f,if(trade)L10n.t("Gehandelte Stückzahl") else L10n.t("Bestand in Stück"),if(trade)"" else Wealth.decimal(p?.num("units") ?: 0,6),true)
        val price=field(f,L10n.t("Kurs je Stück EUR"),Wealth.decimal(p?.num("price") ?: 0,6),true)
        val date=field(f,L10n.t("Kurs- / Handelsdatum"),if(trade)LocalDate.now().toString() else p?.getString("date") ?: LocalDate.now().toString())
        val sell=if(trade)check(f,L10n.t("Verkaufen statt kaufen"),false) else null
        label(f,L10n.t("Stückzahl und Kurs mit höchstens sechs Nachkommastellen. Bestand setzen ist eine Eröffnungs-/Bestandskorrektur ohne Geldbewegung. Käufe und Verkäufe ändern das Verrechnungsguthaben zusätzlich."),14f,color=muted)
        dialog(if(trade)L10n.t("Wertpapierhandel") else L10n.t("Wertpapierbestand"),f) {
            val c=JSONObject().put("op",if(trade)"trade" else "position").put("id",a.num("id")).put("name",name.text.toString()).put("symbol",symbol.text.toString().trim()).put("units",Wealth.scaled(units.text.toString(),6)).put("price",Wealth.scaled(price.text.toString(),6)).put("date",date.text.toString().trim()).put("sell",sell?.isChecked ?: false)
            Wealth.apply(data.wealth,c);change({store.wealthCommand(c)})
        }
    }
    private fun wealthLinkDialog(e:JSONObject) {
        val used=Wealth.events(data.wealth).filter { it.num("id")!=e.num("id") }.flatMap { x -> val a=x.getJSONArray("entries");(0 until a.length()).map { a.getLong(it) } }.toSet()
        val entries=data.entries.filter { it.id !in used && it.kind=="expense" && it.parts.isEmpty() && it.group.isEmpty() && kotlin.math.abs(it.amount)==e.num("amount") }
        val options=listOf(L10n.t("Keine"))+entries.map { ("" + (it.date) + L10n.t(" · ") + (it.merchant) + L10n.t(" · ") + (money(it.amount))) };val ids=listOf(0L)+entries.map { it.id };val linked=e.getJSONArray("entries")
        val f=form();val first=select(f,L10n.t("Bankbuchung"),options,options[ids.indexOf(linked.optLong(0,0)).coerceAtLeast(0)]);val second=select(f,L10n.t("Gegenbuchung (optional)"),options,options[ids.indexOf(linked.optLong(1,0)).coerceAtLeast(0)])
        label(f,L10n.t("Keine neue Geldbewegung. Zugeordnete Bankbuchungen werden in Ausgaben und Diagrammen nicht gezählt. „Keine“ hebt eine bestehende Zuordnung auf."),14f,color=muted)
        dialog(L10n.t("Bankzuordnung"),f) { val a=JSONArray();listOf(ids[first.selectedItemPosition],ids[second.selectedItemPosition]).filter { it>0 }.forEach { a.put(it) };change({store.wealthCommand(JSONObject().put("op","link").put("id",e.num("id")).put("entries",a))}) }
    }
    private fun wealthQuoteDialog(a:JSONObject,p:JSONObject) {
        val f=form();label(f,("" + L10n.t("Alpha Vantage: ein kostenloser Tageskurs-Abruf für ") + (p.getString("symbol")) + L10n.t(". Keine Echtzeitdaten. API-Schlüssel wird nicht gespeichert.")),14f)
        val key=field(f,L10n.t("Kostenloser API-Schlüssel")).apply { inputType=InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD }
        val eur=check(f,L10n.t("Symbol notiert in EUR; kostenlosen Zugang verwenden"),false)
        label(f,L10n.t("Keine automatische Währungsumrechnung. Ohne Schlüssel bleiben manuelle Kurse und alle anderen Funktionen offline nutzbar."),14f,color=muted)
        dialog(L10n.t("Börsenkurs aktualisieren"),f,L10n.t("Abrufen")) { require(eur.isChecked) { L10n.t("EUR-Notierung bestätigen.") };val k=key.text.toString().trim();change({store.refreshWealthQuote(a.num("id"),p.getString("name"),k)}) }
    }
    private fun report(period: String?=month.toString())=Ledger.rows(data.entries,period,effective,data.accounts,data.transfers)
    private fun overview() {
        button(content,L10n.t("Barausgabe")) {
            edit(null,Bundle().apply { putString("payment","Bar");putString("type",L10n.t("Ausgabe")) })
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
        label(stats,("" + (month.format(DateTimeFormatter.ofPattern("MMMM",L10n.locale))) + L10n.t(" · ") + (if(effective) L10n.t("effektiv") else L10n.t("alle Buchungen"))),14f,color=muted)
        label(stats,money(totals.net),32f,true,green);label(stats,L10n.t("Ausgaben nach Erstattungen"),14f,color=muted)
        label(stats,("" + L10n.t("Ausgaben ") + (money(totals.expenses)) + L10n.t("   ·   Erstattungen ") + (money(totals.credits))),14f)
        label(stats,("" + L10n.t("Einnahmen ") + (money(totals.income)) + L10n.t("   ·   Saldo ") + (money(totals.balance))),14f)
        val cats=categoryTotals()
        val card=box(content);label(card,L10n.t("Nach Kategorie"),20f,true)
        if(cats.isEmpty())label(card,L10n.t("Noch keine Ausgaben in diesem Monat."),color=muted)
        cats.forEach { (name,value) -> label(card,("" + (name) + L10n.t("   ") + (money(value)))) }
        val recent=box(content);label(recent,L10n.t("Letzte Buchungen"),20f,true)
        report().take(6).forEach { entryRow(recent,it) }
        if(report().isEmpty())label(recent,L10n.t("Mit + Buchung einen Eintrag anlegen."),color=muted)
    }
    private fun categoryTotals(): List<Pair<String,Long>> {
        if(effective) return report().filter { it.kind!="income" }.flatMap { r -> if(r.parts.isEmpty()) listOf(r.category to r.amount) else r.parts.map { it.category to it.amount } }.groupBy { it.first }.map { (k,v)->k to v.sumOf { it.second } }.filter { it.second!=0L }.sortedByDescending { it.second }
        return data.entries.filter { !it.wealthTransfer && it.date.startsWith(month.toString()) && it.kind!="income" }.flatMap { e -> if(e.parts.isEmpty()) listOf(e.category to e.amount) else e.parts.map { it.category to it.amount } }.groupBy { it.first }.map { (k,v)->k to v.sumOf { it.second } }.filter { it.second!=0L }.sortedByDescending { it.second }
    }
    private fun contributionNote(e:Entry):String {
        val expected=e.expectedContribution ?: return ""
        val diff=Ledger.contributionDifference(e)!!
        return ("" + L10n.t("Vereinbart: ") + (money(expected)) + L10n.t(" · Eingegangen: ") + (money(-e.amount)) + L10n.t(" · "))+if(diff>0) ("" + L10n.t("Überzahlung / Abweichung: ") + (money(diff)) + L10n.t(" zu viel")) else if(diff<0) ("" + (money(-diff)) + L10n.t(" fehlen")) else L10n.t("Betrag stimmt")
    }
    private fun entryRow(parent: LinearLayout,r: ReportRow) {
        val b=column(parent)
        label(b,r.name,17f,true)
        label(b,("" + (r.date) + L10n.t(" · ") + (r.category) + (if(r.grouped) L10n.t(" · Gruppe") else "") + L10n.t("   ") + (money(r.amount))),14f,color=if(r.amount<0)green else muted)
        r.ids.mapNotNull { id->data.entries.find { it.id==id } }.map { contributionNote(it) }.filter { it.isNotEmpty() }.forEach { label(b,it,13f,color=muted) }
        b.setPadding(0,dp(6),0,dp(6));b.setOnClickListener {
            if(r.ids.size==1 && !r.grouped) data.entries.find { it.id==r.ids.first() }?.let { edit(it) }
            else { val entries=r.ids.mapNotNull { id->data.entries.find { it.id==id } };AlertDialog.Builder(this).setTitle(r.name).setItems(entries.map { ("" + (it.date) + L10n.t(" · ") + (it.merchant) + (if(it.kind=="income") L10n.t(" (Einnahme)") else "") + L10n.t(" · ") + (money(it.amount)) + L10n.t("\n") + (contributionNote(it))) }.toTypedArray()) { _,i->edit(entries[i]) }.setNegativeButton(L10n.t("Schließen"),null).show() }
        }
    }
    private fun transactions() {
        val search=field(content,L10n.t("Buchungen durchsuchen"))
        val list=column(content)
        fun render(query: String) { list.removeAllViews(); val rows=report().filter { r->(r.name+" "+r.category+" "+r.ids.mapNotNull { id->data.entries.find { it.id==id }?.notes }.joinToString(" ")).contains(query,true) }
            label(list,("" + (rows.size) + L10n.t(" Einträge")),14f,color=muted);rows.take(300).forEach { entryRow(list,it) };if(rows.size>300)label(list,L10n.t("Erste 300 Einträge. Suche eingrenzen.")) }
        render("");search.addTextChangedListener(object:TextWatcher { override fun beforeTextChanged(s:CharSequence?,start:Int,count:Int,after:Int){};override fun onTextChanged(s:CharSequence?,start:Int,before:Int,count:Int){render(s.toString())};override fun afterTextChanged(e:Editable?){} })
    }
    private fun graphs() {
        val card=box(content);label(card,L10n.t("Letzte zwölf Monate"),20f,true)
        val metric=select(card,L10n.t("Wert"),listOf(L10n.t("Ausgaben nach Erstattungen"),L10n.t("Ausgaben"),L10n.t("Erstattungen"),L10n.t("Einnahmen"),L10n.t("Saldo")))
        val bars=column(card)
        fun render() {
            bars.removeAllViews()
            val values=Ledger.monthRange(month).map { m->val t=Ledger.totals(report(m));m to when(metric.selectedItemPosition){1->t.expenses;2->t.credits;3->t.income;4->t.balance;else->t.net} }
            val max=values.maxOfOrNull { kotlin.math.abs(it.second) }?.coerceAtLeast(1) ?: 1
            values.forEach { (name,value)->bar(bars,name,money(value),value,max) }
        }
        metric.onItemSelectedListener=object:AdapterView.OnItemSelectedListener {override fun onItemSelected(p:AdapterView<*>?,v:View?,position:Int,id:Long){render()};override fun onNothingSelected(p:AdapterView<*>?){} }
        render()
        val cats=box(content);label(cats,("" + L10n.t("Kategorien · ") + (month)),20f,true)
        val totals=categoryTotals();val max=totals.maxOfOrNull { kotlin.math.abs(it.second) }?.coerceAtLeast(1) ?: 1
        totals.forEach { (name,value)->bar(cats,name,money(value),value,max) }
    }
    private fun bar(parent: LinearLayout,name:String,value:String,amount:Long,max:Long) {
        label(parent,("" + (name) + L10n.t("   ") + (value)),14f)
        val track=FrameLayout(this);track.setBackgroundColor(Color.rgb(235,238,232));parent.addView(track,LinearLayout.LayoutParams(-1,dp(9)))
        val fill=View(this);fill.setBackgroundColor(if(amount>=0)green else Color.rgb(180,111,60));track.addView(fill,FrameLayout.LayoutParams(1,-1))
        track.post { fill.layoutParams=FrameLayout.LayoutParams((track.width*kotlin.math.abs(amount).toDouble()/max).toInt().coerceAtLeast(if(amount==0L)0 else 2),-1) }
    }
    private fun settings() {
        val languageBox=box(content)
        label(languageBox,L10n.t("Sprache"),20f,true)
        button(languageBox,if(L10n.language=="en") "English → Deutsch" else "Deutsch → English") {
            getSharedPreferences("language",MODE_PRIVATE).edit().putString("value",if(L10n.language=="en") "de" else "en").apply()
            recreate()
        }
        button(languageBox,L10n.t("Benutzerhandbuch")) {
            val view=android.webkit.WebView(this)
            view.settings.javaScriptEnabled=false
            view.settings.blockNetworkLoads=true
            view.layoutParams=android.view.ViewGroup.LayoutParams(-1,(resources.displayMetrics.heightPixels*0.7).toInt())
            view.loadUrl("file:///android_asset/manual/"+L10n.language+".html")
            android.app.AlertDialog.Builder(this).setTitle(L10n.t("Benutzerhandbuch")).setView(view)
                .setPositiveButton(L10n.t("Schließen"),null).setOnDismissListener { view.destroy() }.show()
        }

        val cats=box(content);label(cats,L10n.t("Kategorien"),20f,true);label(cats,L10n.t("Antippen zum Umbenennen, auch in gespeicherten Einträgen."),13f,color=muted)
        data.categories.forEach { old -> button(cats,old) { val f=form();val name=field(f,"Name",old);dialog(L10n.t("Kategorie umbenennen"),f) { change({store.renameCategory(old,name.text.toString())}) } } }
        button(cats,L10n.t("+ Kategorie")) { nameDialog(true) }
        val payments=box(content);label(payments,L10n.t("Zahlungsmittel"),20f,true)
        data.payments.forEach { name -> val bank=data.accounts.find { it.name==name };val kind=if(bank!=null) L10n.t("Bankkonto") else if((data.paymentTypes[name] ?: if(name=="Bar") "cash" else "other")=="cash") L10n.t("Bargeld") else L10n.t("PayPal / Sonstiges")
            button(payments,("" + (name) + L10n.t(" · ") + (kind))) { paymentDialog(name) }
        }
        button(payments,L10n.t("+ Zahlungsmittel")) { paymentDialog() }
        val transfers=box(content);label(transfers,L10n.t("Umbuchungen"),20f,true)
        data.transfers.forEach { pair -> val a=data.entries.find { it.id==pair.outgoing };val b=data.entries.find { it.id==pair.incoming }
            button(transfers,("" + (a?.payment) + L10n.t(" → ") + (b?.payment) + L10n.t(" · ") + (money(a?.amount ?: 0)) + L10n.t(" · Aufheben"))) { change({store.unlink(pair)}) } }
        label(transfers,L10n.t("Eindeutige Gegenbuchungen mit IBAN- oder Umbuchungshinweis werden automatisch zugeordnet. Andere Vorschläge bitte prüfen."),13f,color=muted)
        data.ignored.forEach { pair -> val a=data.entries.find { it.id==pair.outgoing };button(transfers,("" + L10n.t("Ignorierte Umbuchung ") + (a?.date) + L10n.t(" · ") + (money(a?.amount ?: 0)) + L10n.t(" erneut vorschlagen"))) { change({store.reconsider(pair)}) } }
        button(transfers,L10n.t("Gegenbuchungen suchen")) { work({store.transferCandidates()}) { candidates ->
            if(candidates.isEmpty())toast(L10n.t("Keine passenden Gegenbuchungen innerhalb von drei Tagen."))
            else AlertDialog.Builder(this).setTitle(L10n.t("Umbuchung zuordnen")).setItems(candidates.take(100).map { pair ->
                val a=data.entries.first { it.id==pair.outgoing };val b=data.entries.first { it.id==pair.incoming };("" + (a.date) + L10n.t(" · ") + (a.payment) + L10n.t(" → ") + (b.payment) + L10n.t("\n") + (a.merchant) + L10n.t(" / ") + (b.merchant) + L10n.t(" · ") + (money(a.amount)))
            }.toTypedArray()) { _,i->confirm(L10n.t("Umbuchung bestätigen"),L10n.t("Diese beiden Buchungen werden in der effektiven Ansicht ausgeblendet.")) { change({store.link(candidates[i])}) } }.setNegativeButton(L10n.t("Abbrechen"),null).show()
        } }
        val files=box(content);label(files,L10n.t("Import & Sicherung"),20f,true)
        button(files,L10n.t("Bank-CSV importieren")) { pendingDataset=demo;openDocument(104,"*/*") }
        button(files,L10n.t("Letzten CSV-Import rückgängig machen")) {
            work({store.lastCsvImport()}) { batch ->
                if(batch==null) toast(L10n.t("Kein rückgängig machbarer CSV-Import in diesem Datensatz."))
                else confirm(L10n.t("CSV-Import rückgängig machen?"), ("" + L10n.t("Datensatz: ") + (if(demo) "Demo" else L10n.t("Privat")) + L10n.t(" · ") + (batch.createdAt) + L10n.t("\n\n") + (batch.count) + L10n.t(" noch vorhandene importierte Buchungen werden gelöscht, einschließlich späterer Änderungen, Positionen und Belege. Bereits vorher vorhandene Buchungen bleiben erhalten. Dies kann nicht rückgängig gemacht werden."))) {
                    change({store.revertCsvImport(batch.token)}) { toast(L10n.t("CSV-Import rückgängig gemacht.")) }
                }
            }
        }
        button(files,L10n.t("CSV exportieren")) { pendingDataset=demo;createDocument(102,"text/csv",("" + L10n.t("kassensturz-") + (if(demo) "demo" else "privat") + L10n.t(".csv"))) }
        button(files,L10n.t("Vollständige Sicherung erstellen")) { pendingDataset=demo;createDocument(101,"application/zip",("" + L10n.t("kassensturz-") + (if(demo) "demo" else "privat") + L10n.t("-") + (LocalDate.now()) + L10n.t(".zip"))) }
        button(files,L10n.t("Sicherung wiederherstellen")) { pendingDataset=demo;openDocument(103,"application/zip") }
        label(files,L10n.t("Sicherungen enthalten den ausgewählten Datensatz einschließlich Belegen. Wiederherstellen ersetzt diesen Datensatz. CSV enthält keine Bilder."),13f,color=muted)
        val info=box(content);label(info,L10n.t("Kassensturz für Android"),20f,true);label(info,("" + L10n.t("Version ") + (packageManager.getPackageInfo(packageName,0).versionName) + L10n.t(" · Alle Daten auf diesem Gerät")),14f,color=muted)
    }
    private fun nameDialog(category: Boolean) { val f=form();val name=field(f,"Name");dialog(if(category)L10n.t("Kategorie anlegen") else L10n.t("Zahlungsmittel anlegen"),f) { val value=name.text.toString();require(value.trim().isNotEmpty()) { L10n.t("Name fehlt.") };change({store.addName(value,category)}) } }
    private fun paymentDialog(existing:String?=null) {
        val f=form();val bank=data.accounts.find { it.name==existing };val name=field(f,"Name",existing ?: "");name.isEnabled=existing==null
        val initial=if(bank!=null) L10n.t("Bankkonto") else if((existing?.let { data.paymentTypes[it] } ?: if(existing=="Bar") "cash" else "other")=="cash") L10n.t("Bargeld") else L10n.t("PayPal / Sonstiges")
        val type=select(f,L10n.t("Typ"),listOf(L10n.t("Bargeld"),L10n.t("Bankkonto"),L10n.t("PayPal / Sonstiges")),initial)
        val fields=column(f)
        val iban=field(fields,"IBAN (optional)",bank?.iban ?: "")
        val share=field(fields,L10n.t("Mein Anteil in Prozent"),amountText((bank?.share ?: 10000).toLong()),true)
        val income=check(fields,L10n.t("Anteil auch auf eingehende Beträge anwenden"),bank?.shareIncome ?: true)
        label(fields,L10n.t("Anteile gelten in der effektiven Ansicht. Die IBAN hilft beim Erkennen interner Umbuchungen."),13f,color=muted)
        type.onItemSelectedListener=object:AdapterView.OnItemSelectedListener { override fun onItemSelected(p:AdapterView<*>?,v:View?,position:Int,id:Long){ fields.visibility=if(position==1) View.VISIBLE else View.GONE };override fun onNothingSelected(p:AdapterView<*>?){} }
        fields.visibility=if(type.selectedItemPosition==1) View.VISIBLE else View.GONE
        dialog(L10n.t("Zahlungsmittel"),f) {
            val cleaned=name.text.toString().trim();val kind=listOf("cash","bank","other")[type.selectedItemPosition]
            val account=if(kind=="bank") Account(cleaned,Ledger.cents(share.text.toString()).also { require(it in 0..10000) { L10n.t("Anteil: 0–100 %.") } }.toInt(),income.isChecked,Store.normalizeIban(iban.text.toString())) else null
            val save={ change({store.configurePayment(cleaned,kind,account)}) }
            if(bank!=null && kind!="bank") confirm(L10n.t("Kontotyp ändern?"),L10n.t("IBAN, Kontoanteil und zugehörige Umbuchungszuordnungen werden entfernt. Dies wirkt auf bisherige Auswertungen. Buchungen bleiben erhalten.")) { save() } else save()
        }
    }
    private inner class Editor(val original: Entry?, draft: Bundle? = null) {
        val base=form()
        val type=select(base,L10n.t("Art"),listOf(L10n.t("Ausgabe"),L10n.t("Erstattung / Beitrag"),L10n.t("Einnahme")),draft?.getString("type") ?: if(original?.kind=="income")L10n.t("Einnahme") else if((original?.amount ?: 1)<0)L10n.t("Erstattung / Beitrag") else L10n.t("Ausgabe"))
        val date=field(base,L10n.t("Datum (JJJJ-MM-TT)"),draft?.getString("date") ?: original?.date ?: LocalDate.now().toString()).apply {
            inputType=InputType.TYPE_CLASS_DATETIME or InputType.TYPE_DATETIME_VARIATION_DATE
            setSingleLine(true)
        }
        val merchant=field(base,L10n.t("Bezeichnung"),draft?.getString("merchant") ?: original?.merchant ?: "")
        val amount=field(base,L10n.t("Betrag in Euro (positiv)"),draft?.getString("amount") ?: original?.let { amountText(kotlin.math.abs(it.amount)) } ?: "",true)
        val category=select(base,L10n.t("Kategorie"),data.categories,draft?.getString("category") ?: original?.category ?: "Unkategorisiert")
        val payment=select(base,L10n.t("Zahlungsmittel"),(listOf("")+data.payments+"Bar").distinct(),draft?.getString("payment") ?: original?.payment)
        val group=field(base,L10n.t("Gruppe (optional)"),draft?.getString("group") ?: original?.group ?: "")
        val expectedBox=column(base)
        val expected=field(expectedBox,L10n.t("Vereinbarter Kostenbeitrag in Euro (optional)"),draft?.getString("expected") ?: original?.expectedContribution?.let { amountText(it) } ?: "",true)
        label(expectedBox,L10n.t("Nur für Erstattung / Beitrag. Der tatsächlich erhaltene Betrag oben bleibt maßgeblich; Beleg-Sollbetrag hier eintragen."),13f,color=muted)
        val contributionPreview=label(expectedBox,"",13f,color=muted)
        fun updateContributionPreview() {
            val contribution=type.selectedItemPosition==1
            expectedBox.visibility=if(contribution) View.VISIBLE else View.GONE
            val received=runCatching { Ledger.cents(amount.text.toString()) }.getOrNull()
            val agreed=runCatching { Ledger.cents(expected.text.toString()) }.getOrNull()
            contributionPreview.text=if(contribution && received!=null && agreed!=null && received>0 && agreed>=0) contributionNote(Entry(date="",merchant="",amount=-received,category="",expectedContribution=agreed)) else ""
        }
        val contributionWatcher=object:TextWatcher { override fun beforeTextChanged(s:CharSequence?,start:Int,count:Int,after:Int){};override fun onTextChanged(s:CharSequence?,start:Int,before:Int,count:Int){updateContributionPreview()};override fun afterTextChanged(e:Editable?){} }
        expected.addTextChangedListener(contributionWatcher);amount.addTextChangedListener(contributionWatcher)
        type.onItemSelectedListener=object:AdapterView.OnItemSelectedListener { override fun onItemSelected(p:AdapterView<*>?,v:View?,position:Int,id:Long){updateContributionPreview()};override fun onNothingSelected(p:AdapterView<*>?){} }
        updateContributionPreview()
        val notes=field(base,L10n.t("Notizen"),draft?.getString("notes") ?: original?.notes ?: "",lines=3)
        val parts=mutableListOf<Part>().apply { addAll(original?.parts ?: emptyList()) }
        val partsBox=column(base)
        val receiptLabel=label(base,"")
        var photo: File?=draft?.getString("photo")?.let(::File)
        var removeReceipt=draft?.getBoolean("removeReceipt") ?: false
        var window: AlertDialog?=null
        init {
            draft?.getString("parts")?.let { raw -> parts.clear();val a=org.json.JSONArray(raw);for(i in 0 until a.length()) { val p=a.getJSONObject(i);parts.add(Part(p.getString("name"),p.getLong("amount"),p.getString("category"),if(p.isNull("group"))null else p.getString("group"))) } }
            button(base,L10n.t("+ Position aufteilen")) { partDialog(null) }
            button(base,L10n.t("Belegfoto auswählen (auch HEIC)")) { openDocument(110,"image/*") }
            button(base,L10n.t("Beleg fotografieren")) { capture() }
            button(base,L10n.t("Beleg anzeigen")) { showReceipt() }
            button(base,L10n.t("Text aus Beleg lesen")) { ocr() }
            button(base,L10n.t("Beleg entfernen")) { photo?.delete();photo=null;removeReceipt=true;renderParts() }
            if(original!=null)button(base,L10n.t("Buchung löschen")) { confirm(L10n.t("Buchung löschen?"),L10n.t("Der gespeicherte Beleg wird ebenfalls gelöscht.")) { change({store.delete(original.id)}) { window?.dismiss();editor=null } } }
            renderParts()
        }
        fun renderParts() {
            partsBox.removeAllViews();label(partsBox,("" + L10n.t("Positionen · Summe ") + (money(parts.sumOf { it.amount }))),15f,true)
            parts.forEachIndexed { i,p -> button(partsBox,("" + (p.name) + L10n.t(" · ") + (money(p.amount)) + L10n.t("\n") + (p.category) + L10n.t(" · ") + (p.group ?: L10n.t("Gruppe erben")))) { partDialog(i) } }
            receiptLabel.text=if(photo!=null)L10n.t("Neues Belegfoto bereit") else if(original?.receipt==true && !removeReceipt) L10n.t("Beleg gespeichert") else L10n.t("Kein Belegfoto")
        }
        fun partDialog(index: Int?) {
            val old=index?.let { parts[it] };val f=form();val name=field(f,L10n.t("Position"),old?.name ?: "");val value=field(f,L10n.t("Betrag (Vorzeichen wie Buchung)"),old?.let { amountText(it.amount) } ?: "",true)
            button(f,L10n.t("+/− Vorzeichen wechseln")) {
                val raw=value.text.toString().trim().removePrefix("+")
                val signed=if(raw.startsWith("-")) raw.removePrefix("-") else "-"+raw
                value.setText(signed);value.setSelection(signed.length);value.requestFocus()
            }
            val cat=select(f,L10n.t("Kategorie"),data.categories,old?.category ?: category.selectedItem?.toString())
            val mode=select(f,L10n.t("Gruppenzuordnung"),listOf(L10n.t("Gruppe der Buchung erben"),L10n.t("Keine Gruppe"),L10n.t("Eigene Gruppe")),when { old?.group==null->L10n.t("Gruppe der Buchung erben");old.group.isEmpty()->L10n.t("Keine Gruppe");else->L10n.t("Eigene Gruppe") })
            val g=field(f,L10n.t("Eigener Gruppenname"),old?.group ?: "")
            val d=dialog(L10n.t("Position"),f) {
                val part=Part(name.text.toString().trim(),Ledger.cents(value.text.toString()),cat.selectedItem.toString(),when(mode.selectedItemPosition){0->null;1->"";else->g.text.toString().trim().also { require(it.isNotEmpty()) { L10n.t("Gruppenname fehlt.") } }})
                require(part.name.isNotEmpty()) { L10n.t("Positionsname fehlt.") }
                if(index==null)parts.add(part) else parts[index]=part
                renderParts()
            }
            if(index!=null)button(f,L10n.t("Position entfernen")) { parts.removeAt(index);renderParts();d.dismiss() }
        }
        fun entry(): Entry {
            val value=Ledger.cents(amount.text.toString());require(value>0) { L10n.t("Einen positiven Betrag eingeben; Art bestimmt das Vorzeichen.") }
            return Entry(id=original?.id ?: 0,date=LocalDate.parse(date.text.toString().trim()).toString(),merchant=merchant.text.toString().trim(),amount=if(type.selectedItemPosition==0)value else -value,category=category.selectedItem.toString(),payment=payment.selectedItem.toString(),kind=if(type.selectedItemPosition==2)"income" else "expense",notes=notes.text.toString(),group=group.text.toString().trim(),parts=parts.toList(),counterparty=original?.counterparty ?: "",importKey=original?.importKey,expectedContribution=if(type.selectedItemPosition==1 && expected.text.isNotBlank())Ledger.cents(expected.text.toString()) else null).also { Ledger.validate(it) }
        }
        fun draft() = Bundle().apply {
            putLong("id",original?.id ?: 0);putString("type",type.selectedItem.toString());putString("date",date.text.toString());putString("merchant",merchant.text.toString());putString("amount",amount.text.toString());putString("category",category.selectedItem?.toString());putString("payment",payment.selectedItem?.toString());putString("group",group.text.toString());putString("notes",notes.text.toString());putString("expected",expected.text.toString());putString("photo",photo?.path);putBoolean("removeReceipt",removeReceipt)
            putString("parts",org.json.JSONArray().apply { parts.forEach { p->put(org.json.JSONObject().put("name",p.name).put("amount",p.amount).put("category",p.category).put("group",p.group ?: org.json.JSONObject.NULL)) } }.toString())
        }
        fun showReceipt() { work({photo?.takeIf { it.exists() }?.readBytes() ?: if(!removeReceipt) original?.let { store.receipt(it.id) } else null}) { bytes ->
            if(bytes==null)toast(L10n.t("Kein Beleg vorhanden.")) else { val image=ImageView(this@MainActivity);image.adjustViewBounds=true;image.setImageBitmap(android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.size));val scroll=ScrollView(this@MainActivity);scroll.addView(image);AlertDialog.Builder(this@MainActivity).setTitle(L10n.t("Beleg")).setView(scroll).setPositiveButton(L10n.t("Schließen"),null).show() }
        } }
        fun ocr() { work({photo?.readBytes() ?: if(!removeReceipt) original?.let { store.receipt(it.id) } else null}) { bytes ->
            if(bytes==null) { toast(L10n.t("Zuerst ein Belegfoto auswählen."));return@work }
            val bitmap=android.graphics.BitmapFactory.decodeByteArray(bytes,0,bytes.size)
            val recognizer=TextRecognition.getClient(TextRecognizerOptions.DEFAULT_OPTIONS)
            busy=true
            recognizer.process(InputImage.fromBitmap(bitmap,0)).addOnSuccessListener { text ->
                if(!isDestroyed && editor===this@Editor) {
                    val f=form();val result=field(f,L10n.t("Erkannter Text – bitte prüfen"),text.text,lines=6)
                    val total=Regex("(?im)(?:summe|gesamt|total)[^\\n]*?([0-9]+(?:[. ][0-9]{3})*[,.][0-9]{2})(?![0-9])").find(text.text)?.groupValues?.get(1)
                    val choice=check(f,("" + (if(type.selectedItemPosition==1) L10n.t("Erkannten Betrag als vereinbarten Beitrag übernehmen") else L10n.t("Erkannten Gesamtbetrag übernehmen")) + (total?.let { ("" + L10n.t(" (") + (it) + L10n.t(" €)")) } ?: L10n.t(" (nicht gefunden)"))),false);choice.isEnabled=total!=null
                    dialog(L10n.t("Belegtext"),f,L10n.t("Übernehmen")) { notes.setText((notes.text.toString()+"\n"+result.text.toString()).trim());if(choice.isChecked && total!=null) { if(type.selectedItemPosition==1)expected.setText(amountText(BankCsv.amount(total))) else amount.setText(amountText(BankCsv.amount(total))) } }
                }
            }.addOnFailureListener { if(!isDestroyed)toast(("" + L10n.t("Texterkennung fehlgeschlagen: ") + (it.message))) }.addOnCompleteListener { busy=false;bitmap.recycle();recognizer.close() }
        } }
    }
    private fun edit(original: Entry?, draft: Bundle?=null) {
        if(busy)return
        val restored=original ?: draft?.getLong("id")?.takeIf { it>0 }?.let { id->data.entries.find { it.id==id } }
        val e=Editor(restored,draft);editor=e
        val scroll=ScrollView(this).apply { addView(e.base) }
        val window=AlertDialog.Builder(this).setTitle(if(restored!=null)L10n.t("Buchung bearbeiten") else if(e.payment.selectedItem=="Bar")L10n.t("Neue Barausgabe") else L10n.t("Neue Buchung")).setView(scroll).setNegativeButton(L10n.t("Abbrechen"),null).setPositiveButton(L10n.t("Speichern"),null).create()
        e.window=window
        window.setOnShowListener { window.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener { if(!busy)try { val entry=e.entry();val file=e.photo
            work({store.save(entry,file?.readBytes(),e.removeReceipt);store.snapshot()}) { data=it;file?.delete();editor=null;window.dismiss();screen() }
        } catch(ex:Exception){toast(ex.message ?: L10n.t("Eingaben prüfen."))} } }
        window.setOnCancelListener { if(busy)toast(L10n.t("Vorgang läuft.")) }
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
            startActivityForResult(Intent(MediaStore.ACTION_IMAGE_CAPTURE).apply { putExtra(MediaStore.EXTRA_OUTPUT,uri);addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION or Intent.FLAG_GRANT_READ_URI_PERMISSION);clipData=android.content.ClipData.newRawUri(L10n.t("Beleg"),uri) },111)
        } catch(e:Exception) { toast(("" + L10n.t("Kamera nicht verfügbar: ") + (e.message))) }
    }
    override fun onActivityResult(requestCode:Int,resultCode:Int,result:Intent?) {
        super.onActivityResult(requestCode,resultCode,result)
        if(initialLoad) { deferredResult=Triple(requestCode,resultCode,result);return }
        if(resultCode!=RESULT_OK)return
        val uri=if(requestCode==111)cameraFile?.let(Uri::fromFile) else result?.data
        if(uri==null)return
        if(requestCode in 101..104 && pendingDataset!=null && pendingDataset!=demo) { toast(L10n.t("Datensatz wurde gewechselt. Vorgang bitte erneut starten."));return }
        when(requestCode) {
            101 -> work({ contentResolver.openOutputStream(uri,"wt")?.use { store.backup(it) } ?: error(L10n.t("Zieldatei konnte nicht geöffnet werden.")) }) { toast(L10n.t("Sicherung erstellt.")) }
            102 -> work({ contentResolver.openOutputStream(uri,"wt")?.bufferedWriter(Charsets.UTF_8)?.use { it.write(BankCsv.export(store.snapshot().entries)) } ?: error(L10n.t("Zieldatei konnte nicht geöffnet werden.")) }) { toast(L10n.t("CSV exportiert.")) }
            103 -> work({contentResolver.openInputStream(uri)?.use { Store.inspectBackup(it) } ?: error(L10n.t("Datei konnte nicht geöffnet werden."))}) { summary ->
                val source=when(summary.dataset) { "demo"->"Demo";"private"->L10n.t("Privat");else->L10n.t("nicht angegeben") }
                confirm(("" + (if(demo)"Demo" else L10n.t("Privat")) + L10n.t(" ersetzen?")),("" + L10n.t("Sicherung: ") + (summary.entries) + L10n.t(" Buchungen, ") + (summary.receipts) + L10n.t(" Belege.\nQuelle: ") + (source) + L10n.t(" ") + (summary.createdAt) + L10n.t("\n\nDie Sicherung ersetzt alle Buchungen, Einstellungen und Belege dieses Datensatzes. Vorher eine eigene Sicherung erstellen. Der vollständige Archivinhalt wird beim Wiederherstellen geprüft."))) {
                    change({contentResolver.openInputStream(uri)?.use { store.restore(it) } ?: error(L10n.t("Datei konnte nicht geöffnet werden."))}) { toast(L10n.t("Sicherung wiederhergestellt.")) }
                }
            }
            104 -> work({contentResolver.openInputStream(uri)?.use { Store.readLimited(it,8_000_000) } ?: error(L10n.t("CSV konnte nicht geöffnet werden."))}) { bytes ->
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
        val f=form();val delimiter=select(f,L10n.t("Trennzeichen"),listOf(L10n.t("Semikolon (;)"),L10n.t("Komma (,)"),L10n.t("Tabulator")))
        val account=select(f,L10n.t("Zahlungsmittel"),data.payments)
        label(f,L10n.t("Neue Zahlungsmittel vorher in den Einstellungen anlegen."),13f,color=muted)
        val cat=select(f,L10n.t("Kategorie für importierte Buchungen"),data.categories,"Unkategorisiert")
        val signs=check(f,L10n.t("Bank-Vorzeichen: Abbuchungen negativ"),true)
        val income=check(f,L10n.t("Alle Gutschriften als Einnahmen (statt Erstattungen)"),false)
        label(f,L10n.t("ING-Vorspann wird automatisch erkannt; sonst muss die erste Zeile Spaltennamen enthalten. Im nächsten Schritt Spalten zuordnen und Vorschau prüfen."),14f,color=muted)
        dialog(L10n.t("Bank-CSV"),f,L10n.t("Spalten zuordnen")) {
            val rows=BankCsv.parse(text,when(delimiter.selectedItemPosition){1->',';2->'\t';else->';'})
            require(rows.size>1) { L10n.t("Keine CSV-Daten gefunden.") };require(account.selectedItem!=null) { L10n.t("Konto fehlt.") }
            val tr=BankCsv.isTradeRepublic(rows);val ing=BankCsv.isIng(rows);val vb=BankCsv.isVolksbank(rows)
            val mapping=form();val source=if(vb) select(mapping,L10n.t("Quellkonto in der CSV"),listOf(L10n.t("Bitte auswählen"))+BankCsv.volksbankAccounts(rows)) else null
            if(vb) label(mapping,L10n.t("Volksbank erkannt: Quellkonto und passendes Zahlungsmittel wählen. Gutschriften anschließend als Einnahme oder Erstattung prüfen. Keine eindeutige ID: Teilimporte identischer Buchungen manuell prüfen."),14f,color=muted)
            if(ing) label(mapping,L10n.t("ING erkannt. Spalten und EUR-Vorzeichen automatisch; Verwendungszweck/Referenz als Notizen. Gehalt/Rente als Einnahme. Andere Gutschriften anschließend prüfen. Keine eindeutige ID: Teilimporte identischer Buchungen manuell prüfen."),14f,color=muted)
            if(tr) label(mapping,L10n.t("Trade Republic erkannt. Spalten und Vorzeichen werden automatisch zugeordnet. Nur Karten und Überweisungen; weitere Arten werden ausdrücklich ausgeschlossen."),14f,color=muted)
            val headers=rows.first().mapIndexed { i,h->("" + (i+1) + L10n.t(": ") + (h)) }
            fun guess(vararg words:String)=headers.firstOrNull { h->words.any { h.contains(it,true) } }
            val date=select(mapping,L10n.t("Buchungsdatum"),headers,guess("Buchungstag","Datum","Date"))
            val merchant=select(mapping,L10n.t("Bezeichnung / Verwendungszweck"),headers,guess("Verwendungszweck","Buchungstext","Beschreibung","Merchant"))
            val amount=select(mapping,L10n.t("Betrag"),headers,guess("Betrag","Amount"))
            val iban=select(mapping,L10n.t("Gegenkonto-IBAN (optional)"),listOf(L10n.t("Keine"))+headers)
            if(tr || ing || vb) {
                date.setSelection(rows.first().indexOf(if(vb) "Buchungstag" else if(ing) "Buchung" else "date"))
                merchant.setSelection(rows.first().indexOf(if(vb) "Name Zahlungsbeteiligter" else if(ing) "Auftraggeber/Empfänger" else "name"))
                amount.setSelection(rows.first().indexOf(if(ing || vb) "Betrag" else "amount"))
                iban.setSelection(if(vb) rows.first().indexOf("IBAN Zahlungsbeteiligter")+1 else if(ing) 0 else rows.first().indexOf("counterparty_iban")+1)
                listOf(date,merchant,amount,iban).forEach { it.isEnabled=false }
            }
            dialog(L10n.t("Spalten zuordnen"),mapping,L10n.t("Vorschau")) {
                if(vb) require(source!!.selectedItemPosition>0) { L10n.t("Bitte Quellkonto auswählen.") }
                val provider=if(vb) BankCsv.volksbank(rows,account.selectedItem.toString(),cat.selectedItem.toString(),source!!.selectedItem.toString()) else if(ing) BankCsv.ing(rows,account.selectedItem.toString(),cat.selectedItem.toString()) else if(tr) BankCsv.tradeRepublic(rows,account.selectedItem.toString(),cat.selectedItem.toString()) else null
                val entries=provider?.entries ?: BankCsv.entries(rows,date.selectedItemPosition,merchant.selectedItemPosition,amount.selectedItemPosition,account.selectedItem.toString(),cat.selectedItem.toString(),signs.isChecked,iban.selectedItemPosition-1,income.isChecked)
                require(entries.isNotEmpty()) { L10n.t("Keine unterstützten Buchungen mit Betrag gefunden.\n")+provider?.excluded.orEmpty().joinToString("\n") }
                work({store.previewImport(entries)}) { counts ->
                    confirm(("" + (counts.first) + L10n.t(" neue Buchungen importieren?")), (provider?.excluded?.takeIf { it.isNotEmpty() }?.let { ("" + (it.size) + L10n.t(" ausgeschlossene Zeilen:\n"))+it.joinToString("\n")+"\n\n" } ?: "")+("" + (counts.second) + L10n.t(" bereits vorhandene werden übersprungen.\n\n"))+entries.take(8).joinToString("\n") { ("" + (it.date) + L10n.t(" · ") + (it.merchant) + (if(it.kind=="income") L10n.t(" (Einnahme)") else "") + L10n.t(" · ") + (money(it.amount))) }+L10n.t("\n\nDie Prüfung wird beim Speichern wiederholt. Gutschriften können anschließend als Einnahme oder Erstattung bearbeitet werden.")) {
                        work({val actual=store.importEntries(entries);actual to store.snapshot()}) { (actual,snapshot)->data=snapshot;screen();toast(("" + (actual.first) + L10n.t(" importiert, ") + (actual.second) + L10n.t(" bereits vorhanden."))) }
                    }
                }
            }
        }
    }
}
