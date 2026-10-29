/**
 * Анонимная статистика теста «Широта и опора» (test.html) в Google-таблице.
 * Без имён, контактов, IP и данных устройства: только событие, дата и баллы.
 *
 * Как подключить (≈ 5 минут, один раз):
 * 1. Откройте Google-таблицу, куда писать статистику.
 * 2. В ней: Расширения → Apps Script (важно открыть именно из таблицы).
 *    Удалите всё в редакторе и вставьте этот файл целиком, сохраните.
 * 3. «Начать развертывание» → «Новое развертывание» → тип «Веб-приложение».
 *    Выполнять как: «Я». У кого есть доступ: «Все». «Развернуть», разрешить доступ.
 * 4. URL веб-приложения (заканчивается на /exec) вставьте в test.html в строку var ENDPOINT.
 *
 * Проверка: откройте URL /exec в браузере — должно быть «Работает. Пишу в таблицу …».
 * После правки кода: «Начать развертывание» → «Управление развертываниями» → карандаш →
 * Версия: «Новая версия» → «Развернуть». Ссылка при этом не меняется.
 *
 * Лист «Прохождения» — по строке на каждое начало и окончание теста.
 * Лист «Сводка» — сколько начали, сколько дошли до конца и какие типы получились.
 */

var TYPES = ['Широкая и сильная', 'Широкая, но рассеянная', 'Сильная, но узкая', 'Время собирать себя'];
var HEADERS = ['Дата', 'Событие', 'Тип', 'Богатство, %', 'Сила, %',
  'Широта интересов', 'Связи с людьми', 'Разнообразие ролей', 'Ценности и смыслы',
  'Иерархия мотивов', 'Воля и саморегуляция', 'Автономия', 'Жизнестойкость'];

function doGet() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var text = ss
    ? 'Работает. Пишу в таблицу «' + ss.getName() + '».'
    : 'Скрипт не привязан к таблице. Откройте таблицу → Расширения → Apps Script и вставьте код там.';
  return ContentService.createTextOutput(text);
}

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var d = JSON.parse(e.postData.contents);
    var event = d.event === 'finish' ? 'завершил(а)' : d.event === 'start' ? 'начал(а)' : '';
    if (!event) return ContentService.createTextOutput('skip');
    var type = TYPES.indexOf(d.type) >= 0 ? d.type : '';
    var n = function (v) { var x = Number(v); return v === '' || v == null || !isFinite(x) ? '' : x; };
    var f = d.facets || {};
    sheet_().appendRow([new Date(), event, type, n(d.richness), n(d.strength),
      n(f.r1), n(f.r2), n(f.r3), n(f.r4), n(f.s1), n(f.s2), n(f.s3), n(f.s4)]);
    return ContentService.createTextOutput('ok');
  } finally {
    lock.releaseLock();
  }
}

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName('Прохождения');
  if (!sh) {
    sh = ss.insertSheet('Прохождения');
    sh.getRange(1, 1, 1, HEADERS.length).setValues([HEADERS]).setFontWeight('bold');
    sh.setFrozenRows(1);
  }
  if (!ss.getSheetByName('Сводка')) summary_(ss);
  return sh;
}

function summary_(ss) {
  var sum = ss.insertSheet('Сводка', 0);
  var src = "'Прохождения'!";
  var rows = [
    ['Начали тест', '=COUNTIF(' + src + 'B:B,"начал(а)")'],
    ['Дошли до результата', '=COUNTIF(' + src + 'B:B,"завершил(а)")'],
    ['Доля дошедших', '=IFERROR(B2/B1,0)'],
    ['', ''],
    ['Тип', 'Сколько человек']
  ].concat(TYPES.map(function (t) { return [t, '=COUNTIF(' + src + 'C:C,"' + t + '")']; }))
   .concat([['', ''],
            ['Среднее богатство, %', '=IFERROR(ROUND(AVERAGE(' + src + 'D2:D),0),"")'],
            ['Средняя сила, %', '=IFERROR(ROUND(AVERAGE(' + src + 'E2:E),0),"")']]);
  rows.forEach(function (r, i) {
    sum.getRange(i + 1, 1).setValue(r[0]);
    if (r[1].charAt(0) === '=') sum.getRange(i + 1, 2).setFormula(r[1]);
    else sum.getRange(i + 1, 2).setValue(r[1]);
  });
  sum.getRange('B3').setNumberFormat('0%');
  sum.getRange('A5:B5').setFontWeight('bold');
  sum.setColumnWidth(1, 240);
}
