// Executed by test_pipeline.py via node. Runs the real AppsScript.gs
// against a stubbed spreadsheet, because the button's logic cannot be
// reached from Python and a status row promoted by mistake would be a mess.
// Run the real AppsScript.gs against a stubbed spreadsheet, to check the
// status row can never be promoted by the BUTTON (promote.py is separate code).
const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');

const INBOX_HEADERS = ["Apply?","Bucket","Score","Why","Source","Institution","Department",
  "Position","Fields","City","Country","Deadline","Letters","Link","Why skipped",
  "Both sites","Added","uid"];
const APP_HEADERS = ["Applied","Interview","Flyout","Offer","Institution","City","Department",
  "Position","Field","Deadline","Platform","Application method","Application URL",
  "Application email","Description","Letter Writer 1","Letter Writer 2","Letter Writer 3",
  "Letter Writer 4","Notes","Signal JOE","Signal EJME","uid"];

function row(headers, vals){ return headers.map(h => (h in vals ? vals[h] : "")); }

// a status row exactly as sheet.py writes it, plus one ticked and one unticked listing
const statusRow = row(INBOX_HEADERS, {Institution:"Checked 2026-09-08  ·  2 new today  ·  9 waiting"});
const ticked    = row(INBOX_HEADERS, {"Apply?":true, Bucket:"A", Score:46, Source:"EJM",
                                      Institution:"Bocconi University", Position:"Asst Prof",
                                      Link:"https://econjobmarket.org/positions/1", uid:"ejm:1"});
const unticked  = row(INBOX_HEADERS, {"Apply?":false, Bucket:"skip", Source:"JoE",
                                      Institution:"Some Adjunct Post", uid:"joe:2"});

function makeSheet(name, header, rows, headerRow){
  const grid = [];
  for (let i=1;i<headerRow;i++) grid.push(new Array(header.length).fill(""));
  grid.push(header); rows.forEach(r=>grid.push(r));
  return {
    name, grid, id:1,
    getName(){return name;},
    getLastRow(){
      let n = this.grid.length;
      while (n > 0 && this.grid[n-1].every(c => c === "")) n--;   // trailing blanks
      return n;
    },
    deleteRows(start, howMany){ this.grid.splice(start-1, howMany); },
    getLastColumn(){return header.length;},
    getRange(r,c,nr,nc){ const self=this; return {
      getValues(){ return self.grid.slice(r-1, r-1+(nr||1)).map(x=>x.slice(c-1, c-1+(nc||1))); },
      setValues(v){ v.forEach((rw,i)=>{ self.grid[r-1+i] = rw.slice(); }); return this; },
      clearContent(){ for(let i=0;i<(nr||1);i++) self.grid[r-1+i]=new Array(header.length).fill(""); },
      insertCheckboxes(){ return this; }, setHorizontalAlignment(){ return this; },
      setFontSize(){ return this; }, setFontWeight(){ return this; },
      setRichTextValues(){ return this; },
    };},
  };
}
const inbox  = makeSheet("Inbox",  INBOX_HEADERS, [statusRow, ticked, unticked], 1);
const parked = makeSheet("Parked", INBOX_HEADERS, [], 1);
const apps   = makeSheet("Applications", APP_HEADERS, [], 2);

global.SpreadsheetApp = {
  getActiveSpreadsheet: () => ({
    getSheetByName: n => ({Inbox:inbox, Parked:parked, Applications:apps}[n]),
    getSpreadsheetTimeZone: () => "Europe/Amsterdam",
    toast: (m)=>console.log("  toast:", m),
  }),
  getUi: () => ({ createMenu: () => ({addItem(){return this;}, addToUi(){}}),
                  alert: m => { console.log("  ALERT:", m); } }),
  newRichTextValue: () => ({ setText(){return this;}, setLinkUrl(){return this;}, build(){return {};} }),
};
global.Utilities = { formatDate: () => "2026-09-09" };
eval(src);
promoteTicked();

const uidCol = APP_HEADERS.indexOf("uid");
const written = apps.grid.slice(2).filter(r => r.some(c => c !== ""));
console.log("  rows written to Applications:", written.length);
written.forEach(r => console.log("     uid=" + JSON.stringify(r[uidCol]),
                                 "institution=" + JSON.stringify(r[APP_HEADERS.indexOf("Institution")])));
const leaked = written.some(r => String(r.join(" ")).includes("Checked 2026"));
if (leaked) { console.error("FAIL: the status row was promoted"); process.exit(1); }
if (written.length !== 1 || written[0][uidCol] !== "ejm:1") {
  console.error("FAIL: expected exactly the ticked listing"); process.exit(1); }
console.log("  PASS: status row not promoted");
// B2: the Inbox must end up as header + exactly one status row reporting the action
const inboxBody = inbox.grid.slice(1).filter(r => r.some(c => c !== ""));
console.log("  Inbox rows after promote:", inboxBody.length);
if (inboxBody.length !== 1) {
  console.error("FAIL: expected exactly one status row in the Inbox"); process.exit(1); }
const statusText = String(inboxBody[0][INBOX_HEADERS.indexOf("Institution")]);
console.log("     status row:", JSON.stringify(statusText));
if (!/^Promoted \d+, parked \d+ on \d{4}-\d{2}-\d{2}/.test(statusText)) {
  console.error("FAIL: status row does not report the action"); process.exit(1); }
if (inboxBody[0][INBOX_HEADERS.indexOf("uid")] !== "") {
  console.error("FAIL: status row must carry no uid"); process.exit(1); }

const parkedRows = parked.grid.slice(1).filter(r => r.some(c => c !== ""));
console.log("  rows written to Parked:", parkedRows.length,
  parkedRows.some(r=>String(r.join(" ")).includes("Checked 2026")) ? "FAIL: status leaked" : "(no status leak)");
if (parkedRows.some(r=>String(r.join(" ")).includes("Checked 2026"))) process.exit(1);
if (parkedRows.length !== 1) { console.error("FAIL: expected one parked row"); process.exit(1); }
