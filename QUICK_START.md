# Nodelink - Quick Start Guide

## 🚀 Getting Started in 3 Steps

### Step 1: Install Dependencies

```bash
pip install flask numpy
```

### Step 2: Start the Application

```bash
python app.py
```

### Step 3: Open Browser

Navigate to: `http://localhost:5000`

## 📱 Using the Interface

### PowerUp Bonus Simulation

1. **Configure Parameters** (or use defaults)
   - Total Users: 10,000
   - Max Depth: 7
   - Avg Units: 8

2. **Click "🚀 Run Simulation"**
   - Watch the timer display
   - Cancel if needed

3. **View Results**
   - Summary statistics
   - Rank distribution
   - Heatmap matrix

### Direct Bonus Simulation

1. **Run PowerUp first** (creates shared hierarchy)
2. **Switch to Direct Bonus tab**
3. **Configure NLK/USDN parameters**
4. **Click "🚀 Run Direct Bonus Simulation"**
5. **View 12-month breakdown**

## ⚡ Default Settings

### PowerUp
| Setting | Default |
|---------|---------|
| Users | 10,000 |
| Depth | 7 levels |
| Avg Units | 8 ($200) |
| Promotion | Enabled |

### Direct Bonus
| Setting | Default |
|---------|---------|
| NLK Avg Units | 8 |
| NLK Promo Months | 1, 2 |
| USDN Promo Months | 2, 3, 4 |
| Reinvestment | 100% |

## 🎯 Key Metrics Explained

### Payout Ratio
Total bonuses paid ÷ Total sales/inflow

### USDN Eligible Users
Users with ≥$2,500 cumulative USDN (can earn USDN bonuses)

### Disqualified
Potential bonuses not paid because uplines weren't eligible

### Cascade Bonus
Bonus-on-bonus from reinvested USDN component

## ⚠️ Tips for Free Hosting (Render)

1. **Use 10K users** - Larger sizes may timeout
2. **Enable cache** - Faster subsequent runs
3. **Cancel if stuck** - Use Cancel button
4. **Reset if needed** - Use Reset button

## 🛠️ Troubleshooting

### "Already running" error
Click **Reset** button next to Run

### Timeout
Reduce user count to 10,000 or less

### Memory error
Clear hierarchy and use smaller size

## 📊 Output Files

Results display in browser - no files generated.

## 🔗 Deployment

### Render.com
1. Push to GitHub
2. Connect repo
3. Deploy automatically

### Environment
- Python 3.8+
- Flask
- NumPy

---

**Version**: 2.0.0