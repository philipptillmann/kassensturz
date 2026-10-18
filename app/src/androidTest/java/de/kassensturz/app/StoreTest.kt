package de.kassensturz.app

import android.content.Context
import android.content.ContextWrapper
import android.database.sqlite.SQLiteDatabase
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Before
import org.junit.After
import org.junit.Test
import org.junit.Assert.*
import org.junit.runner.RunWith
import java.io.File
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

@RunWith(AndroidJUnit4::class)
class StoreTest {
    private lateinit var db: Store
    private lateinit var isolated: Context
    private lateinit var folder: File
    @Before fun setUp() {
        val base=InstrumentationRegistry.getInstrumentation().targetContext
        folder=File(base.cacheDir,"test-${System.nanoTime()}").apply { mkdirs() }
        isolated=object: ContextWrapper(base) {
            override fun getDatabasePath(name: String)=File(folder,name)
            override fun openOrCreateDatabase(name: String,mode: Int,factory: SQLiteDatabase.CursorFactory?) = SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name),factory)
            override fun openOrCreateDatabase(name: String,mode: Int,factory: SQLiteDatabase.CursorFactory?,handler: android.database.DatabaseErrorHandler?) = SQLiteDatabase.openOrCreateDatabase(getDatabasePath(name).path,factory,handler)
            override fun deleteDatabase(name: String)=SQLiteDatabase.deleteDatabase(getDatabasePath(name))
        }
        db=Store(isolated,false)
    }
    @After fun tearDown() { db.close();folder.deleteRecursively() }
    private fun entry()=Entry(date="2026-10-01",merchant="Gift",amount=5000,category="Shopping",payment="Bankkarte",group="Gift",notes="Keep me",parts=listOf(Part("A",3000,"Shopping","Gift"),Part("B",2000,"Freizeit","")))
    @Test fun testCsvUndoUpgradeFromVersionTwoRetainsEntries() {
        db.save(entry());db.close()
        SQLiteDatabase.openDatabase(isolated.getDatabasePath("private.sqlite3").path,null,SQLiteDatabase.OPEN_READWRITE).use { sql ->
            sql.execSQL("DROP TABLE csv_undo_entries");sql.execSQL("DROP TABLE csv_undo");sql.version=2
        }
        db=Store(isolated,false)
        assertEquals(1,db.snapshot().entries.size);assertNull(db.lastCsvImport())
        db.importEntries(listOf(entry().copy(importKey="csv:after-upgrade")))
        assertEquals(1,db.lastCsvImport()!!.count)
    }
    @Test fun testCsvUndoKeepsDuplicatesAndManualEntriesAndSurvivesRestart() {
        val old=entry().copy(group="",parts=emptyList(),importKey="csv:old")
        val fresh=old.copy(merchant="New",importKey="csv:new")
        db.importEntries(listOf(old));db.save(old.copy(merchant="Manual",importKey=null))
        db.importEntries(listOf(old,fresh))
        val batch=db.lastCsvImport()!!;assertEquals(1,batch.count)
        db.importEntries(listOf(old,fresh));assertEquals(batch,db.lastCsvImport())
        try { db.importEntries(listOf(fresh.copy(importKey="csv:invalid",category="Missing")));fail("Invalid import") } catch (_: IllegalArgumentException) { }
        assertEquals(batch,db.lastCsvImport())
        db.close();db=Store(isolated,false);assertEquals(batch,db.lastCsvImport())
        assertEquals(1,db.revertCsvImport(batch.token))
        assertEquals(setOf("Gift","Manual"),db.snapshot().entries.map { it.merchant }.toSet())
        assertNull(db.lastCsvImport())
        try { db.revertCsvImport(batch.token);fail("Undo twice") } catch (_: IllegalArgumentException) { }
        assertEquals(1 to 0,db.importEntries(listOf(fresh)))
    }
    @Test fun testCsvUndoStaleConfirmationDeletedRowsAndRestore() {
        val a=entry().copy(group="",parts=emptyList(),importKey="csv:a")
        db.importEntries(listOf(a));val first=db.lastCsvImport()!!
        db.importEntries(listOf(a.copy(importKey="csv:b")))
        try { db.revertCsvImport(first.token);fail("Stale confirmation") } catch (_: IllegalArgumentException) { }
        val current=db.lastCsvImport()!!
        val id=db.snapshot().entries.single { it.importKey=="csv:b" }.id
        db.delete(id);db.save(a.copy(merchant="Manual",importKey=null))
        assertEquals(0,db.revertCsvImport(current.token))
        assertEquals(2,db.snapshot().entries.size)
        db.importEntries(listOf(a.copy(importKey="csv:c")))
        val output=ByteArrayOutputStream();db.backup(output)
        db.restore(ByteArrayInputStream(output.toByteArray()))
        assertNull(db.lastCsvImport());assertEquals(3,db.snapshot().entries.size)
    }
    @Test fun testCrudRestartAndCategoryRename() {
        val id=db.save(entry());db.renameCategory("Shopping","Einkäufe")
        val saved=db.snapshot().entries.single();assertEquals("Einkäufe",saved.category);assertEquals("Einkäufe",saved.parts[0].category)
        db.close();db=Store(isolated,false);assertEquals("Keep me",db.snapshot().entries.single().notes)
        db.save(saved.copy(merchant="Updated"));assertEquals("Updated",db.snapshot().entries.single().merchant)
        db.delete(id);assertTrue(db.snapshot().entries.isEmpty())
    }
    @Test fun testDatasetsAreIndependentAndDemoIsNotReseeded() {
        db.save(entry());val demo=Store(isolated,true)
        try { val rows=demo.snapshot().entries;assertTrue(rows.size>=80);rows.forEach { demo.delete(it.id) };demo.close()
            val reopened=Store(isolated,true);try { assertTrue(reopened.snapshot().entries.isEmpty()) } finally { reopened.close() }
            assertEquals(1,db.snapshot().entries.size)
        } finally { demo.close() }
    }
    @Test fun testBackupRestoreIncludesReceiptsAndAllSettings() {
        val bitmap=android.graphics.Bitmap.createBitmap(40,100,android.graphics.Bitmap.Config.RGB_565)
        val jpeg=ByteArrayOutputStream().apply { bitmap.compress(android.graphics.Bitmap.CompressFormat.JPEG,85,this) }.toByteArray();bitmap.recycle()
        val id=db.save(entry(),jpeg)
        db.configure(Account("Bankkarte",5000))
        val before=db.snapshot();val bytes=ByteArrayOutputStream();db.backup(bytes)
        val summary=Store.inspectBackup(ByteArrayInputStream(bytes.toByteArray()))
        assertEquals(1,summary.entries);assertEquals(1,summary.receipts);assertEquals("private",summary.dataset)
        assertTrue(summary.createdAt.isNotBlank());assertEquals(before,db.snapshot())
        db.delete(id);db.restore(ByteArrayInputStream(bytes.toByteArray()))
        assertEquals(before,db.snapshot());assertTrue(jpeg.contentEquals(db.receipt(id)))
        db.delete(id);assertNull(db.receipt(id))
    }
    @Test fun testInvalidArchiveRollsBackAllChanges() {
        db.save(entry());val before=db.snapshot();val good=ByteArrayOutputStream();db.backup(good)
        val malformed=ByteArrayOutputStream();ZipOutputStream(malformed).use { z->z.putNextEntry(ZipEntry("data.json"));z.write("{\"format\":\"kassensturz-android\",\"version\":99}".toByteArray());z.closeEntry() }
        try { db.restore(ByteArrayInputStream(malformed.toByteArray()));fail("Must reject unknown schema") } catch (_: IllegalArgumentException) { } catch (_: java.util.zip.ZipException) { }
        assertEquals(before,db.snapshot())
        // Valid data followed by an unknown path fails after replacements have begun.
        val zipIn=java.util.zip.ZipInputStream(ByteArrayInputStream(good.toByteArray()));zipIn.nextEntry;val metadata=zipIn.readBytes();zipIn.close()
        val corrupt=ByteArrayOutputStream();ZipOutputStream(corrupt).use { z->z.putNextEntry(ZipEntry("data.json"));z.write(metadata);z.closeEntry();z.putNextEntry(ZipEntry("../escape"));z.write(byteArrayOf(1));z.closeEntry() }
        try { db.restore(ByteArrayInputStream(corrupt.toByteArray()));fail("Must reject unknown path") } catch (_: IllegalArgumentException) { } catch (_: java.util.zip.ZipException) { }
        assertEquals(before,db.snapshot())
    }
    @Test fun testCsvDedupIsAccountScopedAndAtomic() {
        val csv=listOf(listOf("Date","Name","Amount"),listOf("2026-10-01","Shop","-5"),listOf("2026-10-01","Shop","-5"))
        val a=BankCsv.entries(csv,0,1,2,"A","Shopping",true)
        assertEquals(2 to 0,db.previewImport(a));assertTrue(db.snapshot().entries.isEmpty())
        assertEquals(2 to 0,db.importEntries(a));assertEquals(0 to 2,db.importEntries(a))
        assertEquals(0 to 2,db.previewImport(a))
        assertEquals(2 to 0,db.previewImport(BankCsv.entries(csv,0,1,2,"B","Shopping",true)))
        assertEquals(2 to 0,db.importEntries(BankCsv.entries(csv,0,1,2,"B","Shopping",true)))
        try { db.importEntries(listOf(entry(),entry().copy(category="Missing")));fail("Invalid batch must fail") } catch (_: IllegalArgumentException) { }
        assertEquals(4,db.snapshot().entries.size)
    }
    @Test fun testTransferValidationAndDeletion() {
        db.configure(Account("A"));db.configure(Account("B"))
        val a=db.save(entry().copy(group="",parts=emptyList(),payment="A"))
        val b=db.save(entry().copy(group="",parts=emptyList(),payment="B",amount=-5000))
        val pair=Transfer(a,b);assertEquals(listOf(pair),db.transferCandidates());db.link(pair)
        assertTrue(Ledger.rows(db.snapshot().entries,null,true,transfers=db.snapshot().transfers).isEmpty())
        val archive=ByteArrayOutputStream();db.backup(archive);db.restore(ByteArrayInputStream(archive.toByteArray()));assertEquals(listOf(pair),db.snapshot().transfers)
        db.save(db.snapshot().entries.first { it.id==a }.copy(amount=6000));assertTrue(db.snapshot().transfers.isEmpty())
    }
}
