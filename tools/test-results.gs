/**
 * Приём результатов теста «Широта и опора» (test.html) в Google-таблицу.
 *
 * Как подключить (≈ 5 минут, один раз):
 * 1. Создайте новую Google-таблицу, например «Результаты теста».
 * 2. В ней: Расширения → Apps Script. Удалите всё в редакторе и вставьте этот файл целиком.
 *    Если хотите письмо на почту о каждом новом прохождении — впишите адрес в NOTIFY_EMAIL.
 * 3. Нажмите «Начать развертывание» → «Новое развертывание» → тип «Веб-приложение».
 *    Выполнять как: «Я». У кого есть доступ: «Все». Нажмите «Развернуть» и разрешите доступ.
 * 4. Скопируйте URL веб-приложения (заканчивается на /exec)
 *    и вставьте его в test.html в строку  var ENDPOINT = '';
 *
 * Каждое прохождение будет новой строкой на листе «Результаты».
 * В колонке «Ссылка» — страница с полным результатом человека.
 */

var NOTIFY_EMAIL = ''; // например 'you@gmail.com'; пусто — без писем

var HEADERS = ['Дата', 'Имя', 'Telegram', 'E-mail', 'Возраст', 'Тип', 'Богатство, %', 'Сила, %',
  'Широта интересов', 'Связи с людьми', 'Разнообразие ролей', 'Ценности и смыслы',
  'Иерархия мотивов', 'Воля и саморегуляция', 'Автономия', 'Жизнестойкость',
  'Что важно сейчас', 'Ответы', 'Ссылка', 'Согласие на ПД'];

function doPost(e) {
  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    var d = JSON.parse(e.postData.contents);
    var sheet = SpreadsheetApp.getActive().getSheetByName('Результаты') || SpreadsheetApp.getActive().insertSheet('Результаты');
    if (sheet.getLastRow() === 0) {
      sheet.appendRow(HEADERS);
      sheet.setFrozenRows(1);
      sheet.getRange(1, 1, 1, HEADERS.length).setFontWeight('bold');
    }
    var f = d.facets || {};
    var clean = function (v) { return String(v == null ? '' : v).slice(0, 1000).replace(/^[=+\-@]/, "'$&"); };
    sheet.appendRow([new Date(), clean(d.name), clean(d.telegram), clean(d.email), clean(d.age), clean(d.type),
      Number(d.richness) || 0, Number(d.strength) || 0,
      f.r1, f.r2, f.r3, f.r4, f.s1, f.s2, f.s3, f.s4,
      clean(d.note), "'" + clean(d.answers), clean(d.link), d.consent ? 'да' : 'нет']);

    if (NOTIFY_EMAIL) {
      MailApp.sendEmail(NOTIFY_EMAIL, 'Тест «Широта и опора»: ' + clean(d.name),
        [clean(d.name) + ' прошёл(-ла) тест.', 'Тип: ' + clean(d.type),
         'Богатство: ' + d.richness + '%, сила: ' + d.strength + '%',
         'Telegram: ' + clean(d.telegram), 'E-mail: ' + clean(d.email),
         'Что важно: ' + clean(d.note), '', 'Полный результат: ' + clean(d.link)].join('\n'));
    }
    return ContentService.createTextOutput('ok');
  } finally {
    lock.releaseLock();
  }
}
