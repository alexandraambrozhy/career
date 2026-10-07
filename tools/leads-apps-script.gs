/**
 * Приём заявок с лендинга в Google Таблицу «Заявки с сайта».
 *
 * Как подключить (один раз):
 * 1. Откройте таблицу → Расширения → Apps Script.
 * 2. Удалите всё в редакторе и вставьте этот файл целиком. Сохраните.
 * 3. Развернуть → Новое развертывание → тип «Веб-приложение».
 *    Выполнять как: «Я». Доступ: «Все». Нажмите «Развернуть» и разрешите доступ.
 * 4. Скопируйте URL веб-приложения (заканчивается на /exec) и пришлите его.
 */

var NOTIFY_BY_EMAIL = true; // письмо владельцу таблицы о каждой новой заявке
var MAX_LEN = 2000;

function doPost(e) {
  var p = (e && e.parameter) || {};

  // Ловушка для спам-ботов: настоящие посетители это поле не видят.
  if (p.website) return reply_('ok');

  var contact = clean_(p.contact);
  if (!contact) return reply_('error: contact required');

  var row = [
    new Date(),
    clean_(p.interest),
    clean_(p.name),
    contact,
    clean_(p.msg),
    'Новая'
  ];

  var lock = LockService.getScriptLock();
  lock.waitLock(10000);
  try {
    SpreadsheetApp.getActiveSpreadsheet().getSheets()[0].appendRow(row);
  } finally {
    lock.releaseLock();
  }

  if (NOTIFY_BY_EMAIL) {
    MailApp.sendEmail(
      Session.getEffectiveUser().getEmail(),
      'Новая заявка с сайта: ' + (row[2] || contact),
      'Что интересует: ' + row[1] + '\n' +
      'Имя: ' + row[2] + '\n' +
      'Контакт: ' + row[3] + '\n' +
      'Запрос: ' + row[4] + '\n\n' +
      SpreadsheetApp.getActiveSpreadsheet().getUrl()
    );
  }

  return reply_('ok');
}

function doGet() {
  return reply_('Форма заявок работает');
}

// Обрезает длинный текст и не даёт таблице выполнить введённое как формулу.
function clean_(v) {
  v = String(v || '').trim().slice(0, MAX_LEN);
  if (/^[=+\-@]/.test(v)) v = "'" + v;
  return v;
}

function reply_(text) {
  return ContentService.createTextOutput(text).setMimeType(ContentService.MimeType.TEXT);
}
