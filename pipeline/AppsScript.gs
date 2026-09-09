/**
 * Job market pipeline: the Promote button.
 *
 * Install: Extensions -> Apps Script, replace Code.gs with this file, Save,
 * reload the sheet. A "Job Market" menu appears next to Help.
 *
 * No credentials and no network: it only moves rows between tabs. The nightly
 * GitHub Action reads the tabs to learn what you decided, so a row promoted
 * here is never put back in the Inbox.
 *
 * Columns are resolved BY HEADER NAME, never by position. An earlier version
 * hardcoded indexes, so inserting a column into the Inbox would have silently
 * written the wrong fields into Applications, which is the worst failure this
 * script can have. If a header it needs is missing it stops and says so.
 */

var INBOX = 'Inbox', PARKED = 'Parked', APPS = 'Applications';
var APPS_HEADER_ROW = 2;   // Applications keeps "Last updated:" on row 1
var TAB_HEADER_ROW = 1;

var INBOX_NEEDS = ['Apply?', 'Bucket', 'Score', 'Source', 'Institution',
                   'Department', 'Position', 'Fields', 'City', 'Deadline',
                   'Link', 'Both sites', 'uid'];
var APPS_NEEDS = ['Applied', 'Interview', 'Flyout', 'Offer', 'Institution',
                  'City', 'Department', 'Position', 'Field', 'Deadline',
                  'Platform', 'Application method', 'Application URL',
                  'Description', 'Letter Writer 1', 'Letter Writer 2',
                  'Letter Writer 3', 'Letter Writer 4', 'Notes',
                  'Signal JOE', 'Signal EJME', 'uid'];
var APPS_TICKBOXES = ['Applied', 'Interview', 'Flyout', 'Offer',
                      'Letter Writer 1', 'Letter Writer 2', 'Letter Writer 3',
                      'Letter Writer 4', 'Signal JOE', 'Signal EJME'];

function onOpen() {
  SpreadsheetApp.getUi().createMenu('Job Market')
    .addItem('Promote ticked rows', 'promoteTicked').addToUi();
}

/** name -> 1-based column index, read from the sheet's own header row. */
function headerMap_(sheet, headerRow, needs) {
  var width = sheet.getLastColumn();
  var head = sheet.getRange(headerRow, 1, 1, width).getValues()[0];
  var map = {};
  head.forEach(function (h, i) { if (h !== '') map[String(h).trim()] = i + 1; });
  var missing = needs.filter(function (n) { return !map[n]; });
  if (missing.length) {
    throw new Error('"' + sheet.getName() + '" is missing column(s): ' +
                    missing.join(', ') + '. Its headers must match sheet.py.');
  }
  return map;
}

function promoteTicked() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var inbox = ss.getSheetByName(INBOX);
  var parked = ss.getSheetByName(PARKED);
  var apps = ss.getSheetByName(APPS);
  if (!inbox || !parked || !apps) {
    SpreadsheetApp.getUi().alert('Expected tabs named Inbox, Parked and Applications.');
    return;
  }

  var IM, AM;
  try {
    IM = headerMap_(inbox, TAB_HEADER_ROW, INBOX_NEEDS);
    headerMap_(parked, TAB_HEADER_ROW, INBOX_NEEDS);
    AM = headerMap_(apps, APPS_HEADER_ROW, APPS_NEEDS);
  } catch (e) {
    SpreadsheetApp.getUi().alert(String(e.message));
    return;
  }

  var existing = {};
  var lastApp = apps.getLastRow();
  if (lastApp > APPS_HEADER_ROW) {
    apps.getRange(APPS_HEADER_ROW + 1, AM['uid'], lastApp - APPS_HEADER_ROW, 1)
        .getValues().forEach(function (r) { if (r[0]) existing[String(r[0])] = true; });
  }

  var fromInbox = readRows_(inbox, IM);
  var fromParked = readRows_(parked, IM);

  var toPromote = [], toPark = [];
  fromInbox.forEach(function (r) { (r.ticked ? toPromote : toPark).push(r); });
  fromParked.forEach(function (r) { if (r.ticked) toPromote.push(r); });

  var fresh = toPromote.filter(function (r) { return r.uid && !existing[r.uid]; });

  if (fresh.length) {
    var width = apps.getLastColumn();
    var start = Math.max(apps.getLastRow() + 1, APPS_HEADER_ROW + 1);
    apps.getRange(start, 1, fresh.length, width)
        .setValues(fresh.map(function (r) { return toApplicationRow_(r, IM, AM, width); }));
    formatApplications_(apps, AM, start, fresh.length);
  }

  writeRows_(parked, IM, fromParked.filter(function (r) { return !r.ticked; }).concat(toPark));

  // Promoting always empties the Inbox: ticked rows went to Applications,
  // unticked ones to Parked. Leave a line saying so.
  writeRows_(inbox, IM, []);
  var today = Utilities.formatDate(new Date(),
      ss.getSpreadsheetTimeZone(), 'yyyy-MM-dd');
  writeStatus_(inbox, IM, 'Promoted ' + fresh.length + ', parked ' +
               toPark.length + ' on ' + today + '  ·  0 waiting');

  ss.toast(fresh.length + ' promoted, ' + toPark.length + ' parked', 'Job Market', 5);
}

function readRows_(sheet, IM) {
  var last = sheet.getLastRow();
  if (last <= TAB_HEADER_ROW) return [];
  var width = sheet.getLastColumn();
  return sheet.getRange(TAB_HEADER_ROW + 1, 1, last - TAB_HEADER_ROW, width).getValues()
    .filter(function (row) { return row[IM['uid'] - 1]; })
    .map(function (row) {
      return {ticked: row[IM['Apply?'] - 1] === true,
              uid: String(row[IM['uid'] - 1]), row: row};
    });
}

/**
 * Empty a tab's body. Rows are DELETED, not cleared: clearContent() leaves the
 * tickboxes and the row colouring behind, so an emptied Inbox looked like a
 * list whose text had been rubbed out.
 */
function clearBody_(sheet) {
  var last = sheet.getLastRow();
  if (last > TAB_HEADER_ROW) {
    sheet.deleteRows(TAB_HEADER_ROW + 1, last - TAB_HEADER_ROW);
  }
}

/**
 * One row saying what just happened. Not "nothing new today", which would be
 * true by construction the instant you promote and therefore tells you nothing.
 * It reports the action instead, and survives until the next nightly fetch
 * replaces it. No uid and no tickbox, so it can never be promoted.
 */
function writeStatus_(sheet, IM, text) {
  var width = sheet.getLastColumn();
  var row = new Array(width).fill('');
  row[IM['Institution'] - 1] = text;
  sheet.getRange(TAB_HEADER_ROW + 1, 1, 1, width).setValues([row]);
}

function writeRows_(sheet, IM, rows) {
  var width = sheet.getLastColumn();
  clearBody_(sheet);
  if (!rows.length) return;
  var body = rows.map(function (r) {
    var out = r.row.slice(0, width);
    out[IM['Apply?'] - 1] = false;      // nothing is pre-ticked once parked
    while (out.length < width) out.push('');
    return out;
  });
  sheet.getRange(TAB_HEADER_ROW + 1, 1, body.length, width).setValues(body);
  sheet.getRange(TAB_HEADER_ROW + 1, IM['Apply?'], body.length, 1).insertCheckboxes();
}

function toApplicationRow_(r, IM, AM, width) {
  var v = r.row;
  function inbox(name) { return v[IM[name] - 1]; }
  var both = inbox('Both sites');
  var platform = both ? 'JoE + EJM' : inbox('Source');

  var byName = {
    'Applied': false, 'Interview': false, 'Flyout': false, 'Offer': false,
    'Institution': inbox('Institution'), 'City': inbox('City'),
    'Department': inbox('Department'), 'Position': inbox('Position'),
    'Field': inbox('Fields'), 'Deadline': inbox('Deadline'),
    'Platform': platform, 'Application method': platform,
    'Application URL': inbox('Link'),
    'Description': 'bucket ' + inbox('Bucket') + ' · score ' + inbox('Score') +
                   (both ? ' · ' + both : ''),
    'Letter Writer 1': false, 'Letter Writer 2': false,
    'Letter Writer 3': false, 'Letter Writer 4': false,
    'Notes': '',                      // Notes is yours; never written to
    'Signal JOE': false, 'Signal EJME': false,
    'uid': r.uid
  };

  var out = new Array(width).fill('');
  Object.keys(byName).forEach(function (name) { out[AM[name] - 1] = byName[name]; });
  return out;
}

/** Match the Tilburg template: tickboxes, bold institution, real hyperlinks. */
function formatApplications_(apps, AM, startRow, n) {
  APPS_TICKBOXES.forEach(function (name) {
    apps.getRange(startRow, AM[name], n, 1).insertCheckboxes()
        .setHorizontalAlignment('center');
  });
  apps.getRange(startRow, 1, n, apps.getLastColumn()).setFontSize(10);
  apps.getRange(startRow, AM['Institution'], n, 1).setFontWeight('bold');

  var col = AM['Application URL'];
  var rich = apps.getRange(startRow, col, n, 1).getValues().map(function (r) {
    var u = String(r[0] || '');
    var b = SpreadsheetApp.newRichTextValue().setText(u);
    if (u.indexOf('http') === 0) b.setLinkUrl(u);
    return [b.build()];
  });
  apps.getRange(startRow, col, n, 1).setRichTextValues(rich);
}
