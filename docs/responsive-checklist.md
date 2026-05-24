# Responsive UI — Manual device checklist

Test on production or staging after deploy:

**Base URL:** `https://charlesdesouza88-mw-report-copiler-production.up.railway.app`

Use Chrome DevTools device toolbar at **375px** (phone), **768px** (tablet), and **1280px** (desktop). Test one real phone when possible.

| Route | Pass criteria |
|-------|----------------|
| `/login` | No horizontal scroll; submit button full width; inputs do not trigger iOS zoom |
| `/` | Stats readable; hamburger opens/closes drawer; generate button reachable |
| `/students` | Cards on phone (&lt;768px); table on tablet+; turma filter works on both views |
| `/upload` | Hero and CSV panels stack on phone; file picker tappable |
| `/students/new` and edit | Score buttons ≥44px; save visible without zoom |
| `/reports` | Preview / print / download buttons tappable |
| `/reports/preview/...` | Report readable without pinch-zoom; print dialog still OK |

## Pain points to watch

- Topbar actions overflowing behind drawer button
- iOS Safari: file inputs inside dropzones
- Long student names in cards
- Report preview: radar chart clipping (horizontal scroll inside card is OK)

## Automated checks

```bash
pytest
./scripts/smoke_check.sh https://charlesdesouza88-mw-report-copiler-production.up.railway.app
```
