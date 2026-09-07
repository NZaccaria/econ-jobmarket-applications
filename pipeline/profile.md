# Candidate profile

**This is an example. Replace it with your own before your first run.**

Two jobs. The keyword block below is read by the scoring pipeline
(`pipeline/triage.py`) to rank openings. The prose underneath is not read by any
code: it is there so an assistant (or you, in six weeks) knows what the research
actually is when writing a cover letter.

## Research keywords

These are matched against job ads, so they must be words a hiring committee
actually writes in a posting, not the title of your paper. "Prompting" never
appears in an ad; "artificial intelligence" does.

Matching is case-insensitive and on whole words, so `AI` matches "AI" and
"Economics of AI" but not "ch**ai**r" or "tr**ai**ning". Multi-word entries
match as a phrase. The JEL codes apply to JOE ads, which carry them; the text
terms apply to EJM ads, which do not.

Three tiers, best match only, never stacked. Put what you are in tier1, what you
could credibly be hired for in tier2, and genuine but secondary overlap in
tier3.

```yaml
# tier1: the core. Your job market paper and stated field.
tier1:
  terms: [labor economics, labour economics, applied microeconomics,
          personnel economics, human capital]
  jel:   [J2, J3, J6]

# tier2: strong secondary areas, with work behind them.
tier2:
  terms: [econometrics, applied econometrics, causal inference,
          economics of education, health economics, public economics]
  jel:   [C1, C2, C3, I2, H2]

# tier3: peripheral but genuine overlap.
tier3:
  terms: [development economics, political economy, industrial organization,
          behavioral economics, experimental economics]
  jel:   [O1, D7, L1, D9]
```

## Who

Alex Rivera (example), PhD candidate in Economics, Example University
(2021--present). Stated interests: labor economics, applied microeconomics,
economics of education.

Advisors and references: list them here, with institutions. Worth noting where
each one sits: an opening at a reference's own department is not a coincidence
worth missing.

## Papers, and what each one connects to

**Firm Pay Policies and Worker Mobility** (job market paper)
Labor market dynamics, monopsony, wage setting, matched employer-employee data.
Connects to: labor economists working on wage structure or firm heterogeneity,
and anyone using linked administrative data.

**Returns to Vocational Training** (with a coauthor)
Economics of education, human capital, program evaluation, difference in
differences.
Connects to: education economists and applied micro people doing policy
evaluation.

Add one entry per paper. What matters is the second line: the words a committee
in that field would recognise, because those are what the scorer matches on.

## Teaching

What you can credibly teach, at what level, and in which languages. Language
matters more than people expect: a European post often states a local-language
teaching requirement, and that decides whether an application is worth sending.

## Reading the range

If your portfolio spans areas that rarely sit together, say so here and say
which one to lead with for which kind of department. That judgement does not
affect scoring, but it is exactly what you will want written down when you are
tailoring the fortieth cover letter.
