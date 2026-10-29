/**
 * Анонимная статистика теста «Широта и опора» (test.html) в Google-таблице.
 * Без имён, контактов, IP и данных устройства: только событие, дата и баллы.
 *
 * Как подключить (≈ 5 минут, один раз):
 * 1. Создайте новую Google-таблицу, например «Статистика теста».
 * 2. В ней: Расширения → Apps Script. Удалите всё в редакторе и вставьте этот файл целиком.
 * 3. Нажмите «Начать развертывание» → «Новое развертывание» → тип «Веб-приложение».
 *    Выполнять как: «Я». У кого есть доступ: «Все». Нажмите «Развернуть» и разрешите доступ.
 * 4. Скопируйте URL веб-приложения (заканчивается на /exec)
 *    и вставьте его в test.html в строку  var ENDPOINT = '';
 *
 * Лист «Прохождения» — по строке на каждое начало и окончание теста.
 * Лист «Сводка» — сколько начали, сколько дошли до конца и какие типы получились.
 */

var TYPES = ['Широкая и сильная', 'Широкая, но рассеянная', 'Сильная, но узкая', 'Время собирать себя'];
var HEADERS = ['Дата', 'Событие', 'Тип', 'Богатство, %', 'Сила, %',
  'Широта интересов', 'Связи с людьми', 'Разнообразие ролей', 'Ценности и смыслы',
  'Иерархия мотивов', 'Воля и саморегуляция', 'Автономия', 'Жизнестойкость'];

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var d = JSON.parse(e.postData.contents);
    var event = d.event === 'finish' ? 'завершил(а)' : d.event === 'start' ? 'начал(а)' : '';
    if (!event) return ContentService.createTextOutput('skip');
    var type = TYPES.indexOf(d.type) >= 0 ? d.type : '';
    var n = function (v) { var x = Number(v); return isFinite(x) ? x : ''; };
    var f = d.facets || {};
    sheet_().appendRow([new Date(), event, type, n(d.richness), n(d.strength),
      n(f.r1), n(f.r2), n(f.r3), n(f.r4), n(f.s1), n(f.s2), n(f.s3), n(f.s4)]);
    return ContentService.createTextOutput('ok');
  } finally {
    lock.releaseLock();
  }
}

function sheet_() {
  var ss = SpreadsheetApp.getActive();
  var sh = ss.getSheetByName('Прохождения');
  if (sh) return sh;
  sh = ss.insertSheet('Прохождения');
  sh.appendRow(HEADERS);
  sh.setFrozenRows(1);
  sh.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');

  var sum = ss.insertSheet('Сводка', 0);
  var rows = [
    ['Начали тест', '=COUNTIF(\'Прохождения\'!B:B,"начал(а)")'],
    ['Дошли до результата', '=COUNTIF(\'Прохождения\'!B:B,"завершил(а)")'],
    ['Доля дошедших', '=IFERROR(B2/B1,0)'],
    ['', ''],
    ['Тип', 'Сколько человек']
  ].concat(TYPES.map(function (t) { return [t, '=COUNTIF(\'Прохождения\'!C:C,"' + t + '")']; }))
   .concat([['', ''], ['Среднее богатство, %', '=IFERROR(ROUND(AVERAGE(\'Прохождения\'!D2:D),0),"")'],
            ['Средняя сила, %', '=IFERROR(ROUND(AVERAGE(\'Прохождения\'!E2:E),0),"")']]);
  sum.getRange(1, 1, rows.length, 2).setFormulas(rows.map(function (r) { return r.map(String); }));
  sum.getRange('B3').setNumberFormat('0%');
  sum.getRange('A5:B5').setFontWeight('bold');
  sum.setColumnWidth(1, 240);
  return sh;
}
