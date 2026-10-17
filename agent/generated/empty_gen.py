INPUT_CSV = 'C:\\Users\\gaius\\AppData\\Local\\Temp\\querycanvas_sjdhywuu\\result.csv'
OUTPUT_PNG = 'C:\\Users\\gaius\\AppData\\Local\\Temp\\querycanvas_sjdhywuu\\chart.png'

import pandas as pd
import matplotlib.pyplot as plt

# Read the query result CSV
df = pd.read_csv(INPUT_CSV)

# Ensure the expected columns are present
if not {'Product_Category', 'Total_Quantity'}.issubset(df.columns):
    raise ValueError("CSV does not contain required columns.")

# Sort by Total_Quantity descending (already sorted by query, but just in case)
df = df.sort_values('Total_Quantity', ascending=False)

# Identify the best selling category
best_index = df['Total_Quantity'].idxmax()

# Prepare explode to highlight the best category
explode = [0.1 if i == best_index else 0 for i in range(len(df))]

# Create the pie chart
fig, ax = plt.subplots(figsize=(8, 8))
ax.pie(
    df['Total_Quantity'],
    labels=df['Product_Category'],
    autopct='%1.1f%%',
    startangle=90,
    explode=explode,
    shadow=True
)
ax.set_title('Best Selling Product Category in West\n(Quantity Sold)')

# Ensure the pie is a circle
ax.axis('equal')

# Save the figure
plt.tight_layout()
plt.savefig(OUTPUT_PNG, dpi=300)
plt.close(fig)