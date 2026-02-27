# Nodelink - Node Growth Payout Simulator

## Overview

A comprehensive simulation platform for modeling multi-level compensation plans with two bonus programs:

1. **PowerUp Bonus** - Volume-based rank qualification with tiered payouts
2. **Direct Bonus** - NLK and USDN program bonuses with eligibility thresholds

## Features

- **Realistic Hierarchy Generation** - Uses Barabási–Albert preferential attachment model
- **Research-Backed Behavior** - Purchase patterns based on MLM industry research (AARP, FTC studies)
- **Dual Simulation Modes** - PowerUp and Direct Bonus run on shared hierarchy
- **Interactive Web Interface** - Real-time progress tracking with cancel support
- **CSV Caching** - Fast hierarchy reuse for repeated simulations

## Quick Start

### Installation

```bash
pip install flask numpy
```

### Run Locally

```bash
python app.py
```

Open browser to: `http://localhost:5000`

### Deploy to Render

1. Push to GitHub
2. Connect repo to Render
3. Set build command: `pip install flask numpy`
4. Set start command: `python app.py`

## Configuration

### PowerUp Simulation

| Parameter | Default | Description |
|-----------|---------|-------------|
| Total Users | 10,000 | Hierarchy size |
| Max Depth | 7 | Maximum hierarchy levels |
| Avg Units | 8 | Average purchase units ($25 each) |
| Promotion | Enabled | Promotional push simulation |

### PowerUp Matrix (% by Rank × Lines)

| Rank | 1L | 2L | 3L | 4L | 5L |
|------|-----|-----|-----|-----|-----|
| N1 | 3% | 5% | – | – | – |
| N2 | 4% | 6% | – | – | – |
| N3 | 5% | 8% | 10% | – | – |
| N4 | 6% | 11% | 13% | 15% | – |
| N5 | 7% | 12% | 14% | 17% | 19% |
| N6 | 8% | 13% | 16% | 19% | 21% |
| N7 | 9% | 14% | 18% | 21% | 23% |

### Direct Bonus Simulation

| Parameter | Default | Description |
|-----------|---------|-------------|
| NLK Promo Rate | 15% | First 30 days bonus |
| NLK Standard Rate | 10% | After 30 days |
| NLK Promo Months | 1, 2 | Sales push months |
| USDN L1/L2/L3 | 7%/1.5%/1.5% | 3-level bonus rates |
| USDN Eligibility | $2,500 | Minimum USDN to qualify |
| USDN Promo Months | 2, 3, 4 | Investment push months |
| Reinvestment Rate | 100% | Cascade reinvestment |

## Architecture

```
nodelink/
├── app.py                     # Flask web server
├── mlm_simulation.py          # PowerUp simulation engine
├── direct_bonus_simulation.py # Direct Bonus engine
├── templates/
│   └── index.html            # Web interface
└── hierarchy_cache/          # CSV cache for fast reload
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Web interface |
| `/api/run-simulation` | POST | Start PowerUp simulation |
| `/api/run-direct-bonus` | POST | Start Direct Bonus simulation |
| `/api/status` | GET | PowerUp status/results |
| `/api/direct-bonus-status` | GET | Direct Bonus status/results |
| `/api/cancel-simulation` | POST | Cancel running simulation |
| `/api/force-reset` | POST | Reset stuck state |
| `/api/hierarchy-status` | GET | Check loaded hierarchy |
| `/health` | GET | Health check for monitoring |

## Performance

| Users | Generation Time | Memory |
|-------|-----------------|--------|
| 10K | ~2-5 seconds | ~50MB |
| 50K | ~15-30 seconds | ~200MB |
| 100K | ~45-90 seconds | ~400MB |

**Note**: Free tier hosting (Render, etc.) may timeout on large hierarchies. Use 10K users for reliable performance.

## Key Metrics

### PowerUp Output
- Total Sales
- Payout Ratio (PowerUp + Matching / Sales)
- Rank Distribution (N1-N7)
- Line Qualification (1-5 lines)

### Direct Bonus Output
- Total Inflow (NLK + USDN)
- NLK Payout Ratio (~13-14%)
- USDN Payout Ratio (~0.05-0.10%)
- USDN Eligible Users
- Cascade Bonus
- Disqualified Amount

## Research Foundation

The simulation uses research-backed parameters:

- **AARP Foundation 2018**: 66% of MLM participants spend <$1,000 total
- **FTC Studies**: 50% attrition in first year, 90% by year 5
- **Behavioral Economics**: Anchoring effects in promotional pushes
- **Network Theory**: Barabási–Albert model for realistic hierarchies

## Troubleshooting

### "Simulation already running"
Click the **Reset** button or use `/api/force-reset` endpoint.

### Timeout on Render
Reduce total users to 10,000 or lower.

### Memory errors
Clear hierarchy and use smaller user count.

## Version

- **Version**: 2.0.0
- **Last Updated**: February 2026
- **Status**: Production Ready