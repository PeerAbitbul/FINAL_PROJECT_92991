# The 5 Analyst Queries

---

## Q1 — באיזה שפות כותב מפתח מסוים?

**השאלה:** תן לי את top 3 שפות לכל מפתח שמיזג לפחות 10 PRs.

**איך סופרים:**
- מחפשים `PullRequestEvent` עם `action=closed` **ו**-`merged=true`
- השפה נלקחת מ-`payload.pull_request.base.repo.language`
- ה"מפתח" הוא מי **פתח** את ה-PR — מ-`payload.pull_request.user.login` ולא מ-`actor`

**דוגמה לתוצאה:**
| actor | language | merged_prs |
|-------|----------|------------|
| john | Python | 45 |
| john | JavaScript | 23 |
| john | Go | 12 |

---

## Q2 — מי באמת כותב קוד בrepo מסוים?

**השאלה:** לכל אחד מ-top 50 repos לפי PR activity — תן לי top 5 commit authors ו-top 5 pushers זה לצד זה.

**איך סופרים:**
- **Commit author** — זוג ייחודי של `author_name + author_email` מתוך `push_commits`
- **Pusher** — ה-`actor` של ה-`PushEvent`
- מתעלמים מ-`PushEvent` עם `forced=true` — הcommits שם לא משקפים מי כתב מה

**למה זה מעניין:** לעיתים קרובות הpusher והcommit author הם אנשים שונים — bots, maintainers שמאחדים קוד של אחרים.

**דוגמה לתוצאה:**
| repo | top_pushers | top_commit_authors |
|------|-------------|-------------------|
| org/myrepo | john, bot, sara... | sara, mike, alice... |

---

## Q3 — מי עובד טוב עם מי?

**השאלה:** top 10 זוגות מפתחים שתרמו ל-3 repos משותפים לפחות.

**איך סופרים:**
- "תרם לrepo" = הופיע כPR author **או** commit author על אותו repo
- זוג הוא unordered — (john, sara) זה אותו דבר כמו (sara, john)
- ממיינים לפי מספר repos משותפים, שוויון — לפי סך תרומות משותפות

**דוגמה לתוצאה:**
| actor_1 | actor_2 | shared_repos |
|---------|---------|--------------|
| john | sara | 12 |
| mike | alice | 8 |

---

## Q4 — מי שנתן כוכב — האם הפך לתורם?

**השאלה:** לכל repo עם 500+ כוכבים — כמה אחוז מהstargazers עשו fork תוך 2 ימים סימולטיביים, וכמה אחוז מהforkers פתחו PR תוך 5 ימים סימולטיביים?

**איך סופרים:**
- כוכב = `WatchEvent`
- fork = `ForkEvent` על אותו repo על ידי אותו actor תוך 2 ימים מהכוכב
- PR = `PullRequestEvent` עם `action=opened` על אותו repo על ידי אותו actor תוך 5 ימים מה-fork

**חשוב:** הימים הם **סימולטיביים** — לא ימים אמיתיים, ימים בשעון הsimulation.

**דוגמה לתוצאה:**
| repo | stars | star_to_fork_pct | fork_to_pr_pct |
|------|-------|-----------------|----------------|
| org/popular | 1200 | 8.3% | 2.1% |

---

## Q5 — מי מכיר את מי ברשת של מפתח?

**השאלה:** בהינתן actor מסוים — תן לי את כל האנשים שנמצאים במרחק 1 או 2 ממנו, עם הרשימה של הrepos שמחברים ביניהם.

**מה זה מרחק:**
- **מרחק 1** — עבדו על אותו repo
- **מרחק 2** — עבדו על repo עם מישהו שעבד על repo עם ה-seed actor

**הquery חייב להיות פרמטרי** — להחליף את שם ה-actor בזמן ריצה.

**דוגמה לתוצאה:**
| actor | distance | connecting_repos |
|-------|----------|-----------------|
| sara | 1 | org/repoA, org/repoB |
| mike | 2 | org/repoC |
