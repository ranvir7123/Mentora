# Video shortlist: Excel tutorials for Mentora

Made Fri 30 Oct 2026 by the session "The video shortlist", for plan 06 Task 1 (Part B of `docs/superpowers/plans/2026-10-30-06-parallel-parts.md`).

**Ranvir:** each numbered video below is one YouTube tutorial. Approve or strike it. Your answers go in "Ranvir's answers" at the bottom.

## In short

- **18 videos ranked. All 18 carry YouTube's Creative Commons Attribution licence.** That licence means anyone may reuse the video as long as they credit the creator.
- **Top 8 for the lesson library:** ranks 1 to 8.
- **Demo pair:** rank 1 (a monthly budget sheet) and rank 2 (a household spending chart). Both are Creative Commons.
- **Demo backups:** rank 3 (shopping list) and rank 9 (pet survey charts).
- The list is Excel only. VS Code lessons are written by hand, and the Python videos from the first plan were dropped.
- No video was downloaded.

## How the list was made

1. **Search.** I searched YouTube with its Creative Commons filter switched on. In the YouTube app that is Filters → Features → Creative Commons. The searches were everyday tasks: budgets, grade books, shopping lists, payroll, sales totals, charts, COUNTIF, SUMIF, VLOOKUP, IF, percentages, sorting and filtering, loans, and freezing panes.
2. **Licence.** I read the licence on each video's own page. It is the "License" row YouTube shows at the bottom of the description.
   - I read that row from the page's data for every video named in this file.
   - I also saw it on screen for ranks 1, 2, 7 and 9.
   - Every one reads "Creative Commons Attribution license (reuse allowed)".
3. **Facts.** Length, creator, channel, captions, views and upload date all come from the same page's data.
4. **The sheet.** I paused each ranked video at one or two moments and looked at the sheet: which columns it uses, which Excel version, and what gets built.
5. **Width.** Excel gets about 920 px beside the Mentora panel. The starter rule allows columns A to M at normal width, which is about 880 px with the row numbers and scroll bar. "Fits" below means every column I saw sits inside A to M. I judged column widths by eye; I did not measure them.
6. **Checks.** For each video I listed which Excel checks in `app/excel/checks.py` can tell a step is done, and which steps no check can see.

### What the check names mean

| Check | What it can tell |
|---|---|
| `value_equals` | A cell holds the right typed value. |
| `formula` | A cell holds a formula rather than a typed number. It can also require a function (such as SUM), a range the formula must cover, or `$`-locked cells (Excel calls these "absolute" references). |
| `filled_formula` | A formula was copied down a column correctly. |
| `number_format` | Cells show as currency, percent, date, 2 decimals, or whole numbers. |
| `bold` | Cells are bold. |
| `chart` | A column, bar, line or pie chart exists, and can check its range and title. Excel calls upright bars a **column** chart and sideways bars a **bar** chart. |
| `frozen`, `filter`, `sorted`, `selected`, `sheet_named` | Frozen panes, a filter switched on, rows sorted, a range selected, a sheet's name. |

**No check can see:** borders, fill colours, merged cells, conditional formatting (colours that change with the value), cell styles and themes, "Format as Table", chart data labels, column widths, text boxes, sparklines or pivot tables. A lesson made from a video that uses these must leave those steps ungraded or skip them.

**Talking speed was not measured for any video.** YouTube's caption files came back empty in the browser, and the transcript panel never loaded, so I could not count words per minute. The factory gets the captions itself when it fetches a video.

## The picks at a glance

| # | Video | Length | The learner makes | Pick |
|---|---|---|---|---|
| 1 | Excel Practice: Budget Activity | 14:58 | a monthly budget with totals, balance, percentages and a pie chart | **Library + demo** |
| 2 | Excel - bar graph example | 7:12 | a household spending total, one percentage and a chart | **Library + demo** |
| 3 | Excel shopping list | 4:30 | a shopping list with line totals and a grand total | Library, demo backup |
| 4 | Qualitative Frequency Distribution (with COUNTIF) | 9:25 | a frequency table that counts answers with COUNTIF | Library |
| 5 | How to calculate students grades in Excel | 14:46 | a class grade sheet with totals, grades and remarks | Library |
| 6 | Pie chart in Excel | 6:09 | a count table and a titled pie chart | Library |
| 7 | Percentage Discount.avi | 3:55 | ticket prices after discounts, using one locked cell | Library |
| 8 | How to Create Income and Expenses Accounts in Excel Using Running Balance | 14:08 | an income and spending log with a running balance | Library |
| 9 | Pie Charts and Bar Charts in Excel 365 - from a frequency table | 4:42 | a pie chart and a bar chart from a small table | Reserve, demo backup |
| 10 | How To Make A Payroll System In Excel | 5:44 | a pay sheet with overtime, tax and net pay | Reserve |
| 11 | Pie Charts and Bar Charts in Excel 365 - from raw categorical data | 6:03 | counts from a raw list, then two charts | Reserve |
| 12 | How To Create A Concert Tour Budget With Excel | 9:34 | a tour budget with cost lines and a total | Reserve |
| 13 | How to calculate percentage in excel | 5:29 | a marks sheet with totals and percentages | Reserve |
| 14 | Excel — Sorting & filtering | 6:07 | a small table, sorted and filtered | Reserve |
| 15 | How to Make a Basic House Budget Calculator in Excel | 10:45 | a budget against actual spending | Reserve |
| 16 | Make Your Own Gradebook in Minutes With Excel! | 3:59 | a small gradebook with averages | Reserve |
| 17 | L1 ICT Exam E6: Excel explained, sandwich sales analysis with data entry, using SUM & charts | 3:11 | weekly sandwich sales totals and a chart | Reserve |
| 18 | Excel – Grade Calculator | 3:24 | a weighted course grade | Reserve |

All 18 have the licence "Creative Commons Attribution license (reuse allowed)". "Captions by a person" means the creator uploaded written captions. "Auto captions" means YouTube's machine-made ones only.

## Top 8: the lesson library

### 1. Excel Practice: Budget Activity · Library + DEMO
- **Creator:** Red Rocks Community College Math Department, https://www.youtube.com/@RRCCMath
- **Video:** https://www.youtube.com/watch?v=HQOvZNyEJd0
- **Licence:** Creative Commons Attribution. Seen on screen and in the page data.
- **Length:** 14:58 (898 seconds). The factory refuses anything over 900 seconds.
- **Captions:** by a person (English). **Views:** 196. **Uploaded:** 2 Sep 2025.
- **The learner makes:** a one-month budget. It has an income list and an expense list in dollars, SUM totals, a balance (income minus expenses), each expense as a percentage of the total using a `$`-locked total, and a pie chart.
- **Sheet seen:** income in A–B, expenses in D–E, balance in G–H. Excel 365. **Fits.**
- **Checks:** `value_equals` for the amounts; `number_format` currency and percent; `formula` using SUM over each list; `formula` for the balance; `formula` with a locked total plus `filled_formula` for the percentages; `chart` pie.
- **Risks:**
  - It has a borders chapter, and no check can see borders.
  - It is only 2 seconds under the factory's 15-minute limit.
  - It is long for a demo, so the demo should show only a few steps.
  - Few views.
- **Why it ranks first:** the newest Excel, captions by a person, the most check kinds of any video, and a task every learner understands.

### 2. Excel - bar graph example · Library + DEMO
- **Creator:** Jason Lachniet, https://www.youtube.com/@jasonlachniet9527
- **Video:** https://www.youtube.com/watch?v=TGngItVILCs
- **Licence:** Creative Commons Attribution. Seen on screen and in the page data.
- **Length:** 7:12. **Captions:** by a person, plus auto (English). **Views:** 3,913. **Uploaded:** 8 Jan 2020.
- **The learner makes:** a household's monthly spending: six categories in dollars, a SUM total, transport as a percentage of the total, and a chart titled "Monthly budget".
- **Sheet seen (at 1:05 and 3:36):** data in A–B, the question in a text box over F–J, the chart over C–J. Excel 365. **Fits.**
- **Checks:** `value_equals`; `number_format` currency and percent; `formula` using SUM over the six amounts; `formula` for the percentage; `chart` column with a title.
- **Risks:**
  - The video says "bar graph", but its bars stand upright, which Excel calls a **column** chart. The lesson must ask for a column chart, or the check will fail a correct sheet.
  - The question sits in a text box, which no check reads.
  - The workbook holds four example sheets; the lesson should use one.
- **Why it ranks second:** short, current Excel, captions by a person, and one clear question with one right answer.

### 3. Excel shopping list · Library, demo backup
- **Creator:** Paul Adams, https://www.youtube.com/@pauladams3907
- **Video:** https://www.youtube.com/watch?v=ru4ygX3XVNo
- **Licence:** Creative Commons Attribution, from the page data.
- **Length:** 4:30. **Captions:** auto only. **Views:** 23,012. **Uploaded:** 30 Jan 2017.
- **The learner makes:** a shopping list with item, price and quantity, a line total (price × quantity) copied down, and a grand total with SUM (76.15 in the video).
- **Sheet seen:** A–D. Excel 2013. **Fits.**
- **Checks:** `value_equals`; `formula` plus `filled_formula` for the line totals; `formula` using SUM; `number_format` decimal2 or currency (which one is not confirmed).
- **Risks:**
  - It uses fill colours and borders, which no check can see.
  - It has an older Excel look.
  - Auto captions only.
  - An advert played before it in the browser.

### 4. Qualitative Frequency Distribution (with COUNTIF) · Library
- **Creator:** Paul Miller, https://www.youtube.com/@paulmillermath
- **Video:** https://www.youtube.com/watch?v=u7LBpmwNQGE
- **Licence:** Creative Commons Attribution, from the page data.
- **Length:** 9:25. **Captions:** by a person (English). **Views:** 58,290. **Uploaded:** 11 Jun 2018.
- **The learner makes:** a frequency table. It counts how often each party appears in a list of about 77 answers using COUNTIF, adds a total, and works out each party's share.
- **Sheet seen:** the raw list in column A, the table in C–E (Party, Frequency, Relative Frequency). Excel 2016. **Fits.**
- **Checks:** `formula` using COUNTIF with a locked list range, plus `filled_formula`; `formula` using SUM; `number_format` for the shares (percent or 2 decimals, not confirmed which); `sorted`, because the video sorts the list at one point.
- **Risks:**
  - The starter sheet must hold about 77 rows of raw data.
  - The maths-class words ("qualitative", "relative frequency") need plain wording in the lesson.

### 5. How to calculate students grades in Excel · Library
- **Creator:** AdjoTech, https://www.youtube.com/@adjotech
- **Video:** https://www.youtube.com/watch?v=bbJQ3quLPj4
- **Licence:** Creative Commons Attribution, from the page data.
- **Length:** 14:46. **Captions:** by a person (US English). **Views:** 250,840, the most on this list. **Uploaded:** 7 Feb 2021.
- **The learner makes:** a class grade sheet. It totals the quizzes and the final with SUM, gives a letter grade and a remark with IF formulas, and copies them down.
- **Sheet seen:** A–H (NUMBER, NAME, QUIZ 1, QUIZ 2, FINAL, TOTAL, GRADE, REMARK). Excel 2016. **Fits.**
- **Checks:** `formula` using SUM plus `filled_formula`; `formula` using IF plus `filled_formula`; `value_equals` on chosen students' grades.
- **Risks:**
  - It is long.
  - The merged title cell and fill colours cannot be checked.
  - The remark formula I saw, `=IF(F4>=90,"Satisfactory",IF(F4>=80,"Excellent",…`, gives a weaker word to a higher score. That may be a mistake in the video and is worth a look before using.
  - IF formulas nested inside each other are hard for beginners.

### 6. Pie chart in Excel · Library
- **Creator:** Jason Lachniet, https://www.youtube.com/@jasonlachniet9527
- **Video:** https://www.youtube.com/watch?v=FnJtqbkx7s0
- **Licence:** Creative Commons Attribution, from the page data.
- **Length:** 6:09. **Captions:** by a person (English). **Views:** 237. **Uploaded:** 3 Feb 2021.
- **The learner makes:** a table counting sweets by colour, a SUM total (424), and a titled pie chart.
- **Sheet seen (at 1:45):** the table in B–C, the chart over D–L. Excel 2016. **Fits.**
- **Checks:** `value_equals`; `formula` using SUM; `chart` pie with a title.
- **Risks:**
  - The percentage labels on the pie cannot be checked.
  - The data names a sweet brand (Skittles). That is harmless, but the lesson could rename it.
  - It is a small task.

### 7. Percentage Discount.avi · Library
- **Creator:** mrimpeyteaching, https://www.youtube.com/@mrimpeyteaching
- **Video:** https://www.youtube.com/watch?v=ifTW0qeTiSY
- **Licence:** Creative Commons Attribution. Seen on screen and in the page data.
- **Length:** 3:55. **Captions:** auto only. **Views:** 6,282. **Uploaded:** 12 Mar 2012.
- **The learner makes:** theatre ticket prices after each person's discount. One cost per person (£12.00) sits in F3, and `=$F$3-($F$3*B5%)` is copied down.
- **Sheet seen:** A–C plus E–F. Excel 2010. **Fits.**
- **Checks:** `formula` with F3 locked, plus `filled_formula`; `number_format` currency (£ counts); `value_equals` for the cost.
- **Risks:**
  - Old Excel and a low-quality picture.
  - Auto captions only.
- **Why it stays in:** it teaches the `$` lock, the step learners most often get wrong.

### 8. How to Create Income and Expenses Accounts in Excel Using Running Balance · Library
- **Creator:** Template Warriors, https://www.youtube.com/@TemplateWarriors1
- **Video:** https://www.youtube.com/watch?v=MJq1HBtCOCA
- **Licence:** Creative Commons Attribution, from the page data.
- **Length:** 14:08. **Captions:** auto only. **Views:** 66,646. **Uploaded:** 19 Feb 2024.
- **The learner makes:** an income and spending log. Each row's balance is the last balance plus income minus expenses, copied down.
- **Sheet seen:** A–E (DATE, DESCRIPTION, INCOME, EXPENSES, BALANCE), with 2-decimal numbers. **Fits.**
- **Checks:** `formula` plus `filled_formula` for the running balance; `number_format` date and decimal2; `value_equals` for the final balance.
- **Risks:**
  - It is long.
  - The description advertises the channel's template. Credit the video, but don't link the template.
  - Auto captions only.

## Reserves (ranks 9 to 18)

These are spares if a top-8 video gets struck or fails in the factory. All are Creative Commons Attribution, read from the page data.

### 9. Pie Charts and Bar Charts in Excel 365 - from a frequency table · demo backup
- Red Rocks Community College Math Department, https://www.youtube.com/@RRCCMath · https://www.youtube.com/watch?v=_DKgAcwTDMw
- 4:42 · captions by a person · 129 views · 9 Sep 2025 · licence also seen on screen.
- **Makes:** a pie chart and a bar chart from a small typed table of favourite pets.
- **Sheet:** A–B. Excel 365. **Fits.**
- **Checks:** `value_equals`; `chart` pie and `chart` bar with titles.
- **Risks:** no formulas at all, so it is thin as a lesson, and it overlaps rank 6.

### 10. How To Make A Payroll System In Excel
- AdjoTech, https://www.youtube.com/@adjotech · https://www.youtube.com/watch?v=GkLxoJqCeYA
- 5:44 · auto captions · 36,371 views · 5 Jun 2023.
- **Makes:** a pay sheet: pay from hours and rate with overtime, 15% income tax, deductions, net pay, and a total row.
- **Sheet:** A–I with widened columns. By my estimate it is about 830 px, which is tight against 920.
- **Checks:** `formula` plus `filled_formula`; `formula` using SUM; `number_format`.
- **Risks:**
  - The width is tight.
  - Its "Accounting" number format without a money sign may not match any `number_format` kind (not confirmed).
  - The merged title and fill colours cannot be checked.

### 11. Pie Charts and Bar Charts in Excel 365 - from raw categorical data
- Red Rocks Community College Math Department, https://www.youtube.com/@RRCCMath · https://www.youtube.com/watch?v=uqDyonD5Bn0
- 6:03 · captions by a person · 136 views · 9 Sep 2025.
- **Makes:** counts from a raw list with COUNTIF, then a pie chart and a bar chart.
- **Sheet:** data in A–C, the table in G–H. Excel 365. **Fits.**
- **Checks:** `formula` using COUNTIF plus `filled_formula`; `chart` pie and bar; `filter`.
- **Risks:** it counts over a whole column, `=COUNTIF(A:A,G4)`. Whether the check's "covers" test accepts a whole column is not confirmed.

### 12. How To Create A Concert Tour Budget With Excel
- Live Music Business, https://www.youtube.com/@Livemusicbusiness · https://www.youtube.com/watch?v=3hOSlsDINR4
- 9:34 · auto captions · 8,601 views · 27 Apr 2015.
- **Makes:** a tour budget. Each cost line is unit cost × two multipliers, with a SUM total (`=SUM(H3:H24)`).
- **Sheet:** A–H (Item, Supplier, Notes, Unit cost, Multiplier 1, Multiplier 2, Total). **Fits.**
- **Checks:** `formula` plus `filled_formula`; `formula` using SUM over H3:H24.
- **Risks:** the video is zoomed out, so the text is small, and the theme is niche.

### 13. How to calculate percentage in excel
- AdjoTech, https://www.youtube.com/@adjotech · https://www.youtube.com/watch?v=qrLz8-pOZTg
- 5:29 · auto captions · 1,475 views · 5 Apr 2021.
- **Makes:** a marks sheet with a total of five subjects and a percentage, `=(K5/500)*100`.
- **Sheet:** D–L. **Fits**, but it is 9 columns wide.
- **Checks:** `formula` using SUM plus `filled_formula`; `value_equals`.
- **Risks:** it multiplies by 100 instead of using the percent format, so the percent `number_format` check does not apply. The width is tight if columns get widened.

### 14. Excel — Sorting & filtering
- Susanne Flach, https://www.youtube.com/@susanneflach3442 · https://www.youtube.com/watch?v=sEN5BUFn0m8
- 6:07 · auto captions · 350 views · 16 Nov 2020.
- **Makes:** a small table of people, sorted and filtered.
- **Sheet:** A–H. Excel for Mac. **Fits.**
- **Checks:** `sorted`; `filter`.
- **Risks:**
  - It teaches a skill rather than something the learner makes.
  - Mac menus differ from Windows.
  - The presenter's webcam covers a corner.
  - "Format as Table" cannot be checked.

### 15. How to Make a Basic House Budget Calculator in Excel
- The Tech Life, https://www.youtube.com/@thetechlife411 · https://www.youtube.com/watch?v=SU1R-FWPyHY
- 10:45 · auto captions · 74 views · 4 Oct 2026.
- **Makes:** a monthly budget against actual spending, the difference, and money left over ($750), then copies it for the next month.
- **Sheet:** A–D, with the copy in G–J. **Fits.**
- **Checks:** `formula` plus `filled_formula`; `formula` using SUM; `number_format` currency.
- **Risks:**
  - The red highlights look like conditional formatting, which cannot be checked.
  - The channel posts many new videos with few views each and may be machine-made (not confirmed).

### 16. Make Your Own Gradebook in Minutes With Excel!
- Smart Slide Studio(3S), https://www.youtube.com/@slider54 · https://www.youtube.com/watch?v=_kuuKmaJIL0
- 3:59 · auto captions · 1,599 views · 22 May 2025.
- **Makes:** a gradebook with an Average column for three students.
- **Sheet:** A–F. **Fits.**
- **Checks:** `formula` plus `filled_formula` for the average (that it uses AVERAGE is my guess from the column name); `bold`.
- **Risks:**
  - It uses "Format as Table", which cannot be checked.
  - It has only three students.
  - The voice and burned-in captions look machine-made (my guess, not confirmed).

### 17. L1 ICT Exam E6: Excel explained, sandwich sales analysis with data entry, using SUM & charts
- Vocaboard, https://www.youtube.com/@vocaboard · https://www.youtube.com/watch?v=6uYTffxatHc
- 3:11 · auto captions · 11 views · 23 Sep 2024.
- **Makes:** weekly sales totals per sandwich (Monday to Friday) and a chart.
- **Sheet:** the table in B–H and the exam instructions in J–M. **Fits.**
- **Checks:** `formula` using SUM plus `filled_formula`; `chart`.
- **Risks:**
  - The presenter's face covers part of the sheet.
  - It squeezes a whole exam task into 3 minutes, so it is probably quick (not measured).
  - It uses "Format as Table" in a workbook with many sheets.

### 18. Excel – Grade Calculator
- Mike Rozinski, https://www.youtube.com/@mikerozinski5038 · https://www.youtube.com/watch?v=nsJ1m7UcV3c
- 3:24 · auto captions · 93 views · 29 Jun 2022.
- **Makes:** a weighted course grade.
- **Sheet:** A–H, shown beside a course website.
- **Risks:** half the screen is a course website (MyOpenMath), the Excel part is small, and it is tied to one course.

## Left out, and why

All of these show the Creative Commons Attribution licence too; they fail on something else.

| Video | Creator | Why it is out |
|---|---|---|
| [6.2 Sales Rep sales dollars using SUMIFS in Excel](https://www.youtube.com/watch?v=zKx7uRtDnzc) | Dr. Dawn : Stats, Data and AI | Too wide: summary tables run past column N, in a workbook with many sheets. |
| [Excel Family Budget](https://www.youtube.com/watch?v=t0ZGVvB5iXo) | ryan lowe | Too wide: months January to December run across the columns. Old Mac Excel. |
| [Create a Family Budget in Excel – Fast & Simple!](https://www.youtube.com/watch?v=6WgJBlMuTS8) | Apt Observations | It shows the same footage as ryan lowe's 2012 video, so it is probably a re-upload (not confirmed). It is too wide for the same reason. |
| [How to Calculate Attendance Percentage in Excel](https://www.youtube.com/watch?v=K8E8NQBYot0) | How to Learn Excel | Too wide: 31 day columns, out to AJ. |
| [Excel Exercise 2- Sum, Max, Min, Ave & Rank](https://www.youtube.com/watch?v=T5sqnaRpxRM) | SkillsetHome | Too wide (A–N) with 1,000 rows. |
| [VLOOKUP Staff Payroll Exercise (UPDATED!)](https://www.youtube.com/watch?v=_oEDTw4BzQQ) | MPT | Google Sheets, not Excel. |
| [Monthly Budget Google Sheets - PART 1](https://www.youtube.com/watch?v=2uyZhhnBWKI) | MPT | Google Sheets, not Excel. |
| [Basic spreadsheet use - Part 1 (modelling a savings account with interest)](https://www.youtube.com/watch?v=yigwcgLagsw) | Chris Heddles | Google Sheets, not Excel. |
| [Budgeting in Excel Spreadsheet](https://www.youtube.com/watch?v=S0JY6h1IKTc) | Peso Lessons | Its description names a different original owner, so it is a re-upload. It also uses Google Sheets. |
| [Free Inventory Spreadsheet](https://www.youtube.com/watch?v=qEXPVFpCEqI) | La Vie Vintage Rose | LibreOffice, not Excel. |
| [Calculating Your Final Grade](https://www.youtube.com/watch?v=HsWS4ckIjVM) | The Random Professor | Made for one class; it says so itself. |
| [BPC110 Excel Practice 1](https://www.youtube.com/watch?v=fwG1z7fAryY) | PVCCOERSpecialist | Most steps are cell styles, themes, chart styles and sparklines, which no check can see. |
| [Excel tip: Fixing or Freezing specific Columns and Rows](https://www.youtube.com/watch?v=54RTJJEZWdw) | kovolff | A single 2-minute tip, not something the learner makes. I did not look at its sheet. |
| Roel Van de Paar videos | Roel Van de Paar | Slideshows of forum questions, not someone working in Excel. |

## What I could not confirm

- **Talking speed** for every video (see above).
- **Exact column widths.** I judged them by eye from paused frames.
- **The licence row on screen** for 14 of the 18. For those I read it from the page's data, which is what YouTube draws that row from.
- Whether the "covers" test accepts a whole-column range like `A:A` (rank 11).
- Whether "Accounting" format without a money sign counts as currency (rank 10).
- Which number format ranks 3 and 4 use.
- Whether rank 5's remark formula really has the words the wrong way round, or I caught it mid-edit.
- Whether ranks 15 and 16 are machine-made.
- Whether "Create a Family Budget in Excel – Fast & Simple!" is a re-upload of ryan lowe's video.
- `app/ui/demo_backend.py` already names the video https://www.youtube.com/watch?v=k7RM-ot2NWY. I did not check that video or compare it with this list.

## How to credit a video

The Creative Commons Attribution licence asks for a credit. A line in this shape covers it:

> "Excel Practice: Budget Activity" by Red Rocks Community College Math Department, https://www.youtube.com/watch?v=HQOvZNyEJd0, Creative Commons Attribution licence.

## Ranvir's answers

Waiting for Ranvir.
