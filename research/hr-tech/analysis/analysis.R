# Анализ пилотных данных «Карьерного профиля» (IPIP-50, черновая русская форма)
# Запуск: установить R (cran.r-project.org) и RStudio, затем один раз
#   install.packages(c("psych", "lavaan", "readr"))
# Положить выгрузку из базы рядом с этим файлом как pilot.csv (разделитель «;»,
# столбцы E1..O10 с ответами 1–5, без имён и почты) и выполнить скрипт целиком.
# Если pilot.csv нет, скрипт сгенерирует учебные данные, чтобы можно было потренироваться.

library(psych)
library(lavaan)

items <- read.csv2("../prototype/items-ipip50.csv", encoding = "UTF-8")
domains <- c("E", "A", "C", "N", "O")

if (file.exists("pilot.csv")) {
  raw <- read.csv2("pilot.csv")
} else {
  message("pilot.csv не найден: генерирую учебные данные N = 300")
  set.seed(1)
  n <- 300
  traits <- matrix(rnorm(n * 5), n, 5, dimnames = list(NULL, domains))
  raw <- sapply(seq_len(nrow(items)), function(i) {
    d <- items$domain[i]
    k <- ifelse(items$key[i] == "+", 1, -1)
    x <- 0.7 * k * traits[, d] + rnorm(n, sd = 0.7)
    as.integer(cut(x, c(-Inf, -1.2, -0.4, 0.4, 1.2, Inf)))
  })
  colnames(raw) <- items$id
  raw <- as.data.frame(raw)
}

# 1. Чистка: убираем анкеты с проваленной проверкой внимания и одинаковыми ответами подряд
if ("attention_ok" %in% names(raw)) raw <- raw[raw$attention_ok %in% c(TRUE, "TRUE", 1), ]
X <- raw[, items$id]
longest_run <- apply(X, 1, function(r) max(rle(r)$lengths))
X <- X[longest_run < 12, ]
cat("Анкет после чистки:", nrow(X), "\n")

# 2. Переворот обратных пунктов: 6 − ответ
rev_ids <- items$id[items$key == "-"]
X[rev_ids] <- 6 - X[rev_ids]

# 3. Надёжность по каждой шкале: альфа Кронбаха и омега
#    Ориентир: ≥ 0,70 — приемлемо для исследования, ≥ 0,80 — хорошо
for (d in domains) {
  ids <- items$id[items$domain == d]
  a <- psych::alpha(X[ids], warnings = FALSE)
  o <- psych::omega(X[ids], nfactors = 1, plot = FALSE)
  cat(sprintf("%s: альфа = %.2f, омега = %.2f\n", d, a$total$raw_alpha, o$omega.tot))
  # Пункты, которые плохо связаны со шкалой (r.drop < 0,30), — кандидаты на правку перевода
  weak <- rownames(a$item.stats)[a$item.stats$r.drop < 0.30]
  if (length(weak)) cat("   слабые пункты:", paste(weak, collapse = ", "), "\n")
}

# 4. Эксплораторный факторный анализ: распадаются ли 50 пунктов на 5 групп
psych::fa.parallel(X, fa = "fa", main = "Сколько факторов в данных")
efa <- psych::fa(X, nfactors = 5, rotate = "oblimin", fm = "ml")
print(efa$loadings, cutoff = 0.30, sort = TRUE)

# 5. Конфирматорный факторный анализ: проверяем заранее заданную модель из 5 факторов
model <- paste(sapply(domains, function(d)
  paste0(d, " =~ ", paste(items$id[items$domain == d], collapse = " + "))), collapse = "\n")
cfa_fit <- lavaan::cfa(model, data = X, ordered = items$id, estimator = "WLSMV")
print(lavaan::fitMeasures(cfa_fit, c("cfi.scaled", "tli.scaled", "rmsea.scaled", "srmr")))
# Ориентиры: CFI и TLI ≥ 0,90 (лучше ≥ 0,95), RMSEA ≤ 0,08 (лучше ≤ 0,06), SRMR ≤ 0,08.
# Для 50-пунктовых личностных опросников CFA часто не дотягивает до этих порогов,
# это нормально и описывается в техническом отчёте честно.

# 6. Бета-нормы: процентили по пилотной выборке
scores <- sapply(domains, function(d) rowMeans(X[items$id[items$domain == d]]))
norms <- apply(scores, 2, quantile, probs = c(.10, .25, .50, .75, .90))
print(round(norms, 2))
write.csv2(round(norms, 3), "norms-beta.csv")
cat("Готово: norms-beta.csv записан. Подпись в отчёте: «по пользователям сервиса, N =", nrow(X), "»\n")
