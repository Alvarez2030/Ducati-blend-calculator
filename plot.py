import matplotlib.pyplot as plt

# --- your data ---
batches_phil_1 = ["1096", "61", "1228", "1203", "1202", "173", "1060", "57", "1004", "103", "1064"]
visc_phil_1     = [9.722, 5.511, 7.849, 7.337, 6.52, 5.748, 8.635, 5.82, 7.357, 6.921, 7.52]

batches_phil_2 = ["1047", "91", "1069", "362", "17", "1257", "188", "1212", "1200", "1249", "1064"]
visc_phil_2     = [9.722, 5.511, 7.849, 7.337, 6.52, 5.748, 8.635, 5.82, 7.357, 6.921, 7.52]

batches_software_1 = ["V137345_2", "V137352_1", "V137352_3", "V137355_3", "V137364_3", "V137365_2", "V137927_1", "V137927_2", "V137927_3", "V137927_1", "V137365_2"]
visc_software_1 = [5.186, 7.357, 6.921, 4.933, 8.635, 5.748, 7.849, 7.337, 7.52, 7.849, 5.748]

batches_software_2 = ["V131762_3", "V137352_1", "V137352_2", "V137352_3", "V137355_1", "V137355_2", "V137364_2", "V137364_2", "V137365_1", "V137927_2", "V137927_3", "V137365_1"]
visc_software_2 = [5.555, 7.357, 5.71, 6.921, 5.507, 5.71, 9.722, 9.722, 6.52, 7.337, 7.52, 6.52]


batches_all = [
    "V131762_3", "V131762_3", "V131763_3",
    "V137345_1", "V137345_2", "V137345_2",
    "V137352_1", "V137352_2", "V137352_3",
    "V137352_3",
    "V137355_1", "V137355_1", "V137355_2", "V137355_3",
    "V137364_2", "V137364_2", "V137364_3",
    "V137365_1", "V137365_2", "V137365_3",
    "V137365_3",
    "V137927_1", "V137927_2", "V137927_3"
]


visc_all_batches = [
    5.555, 5.555, 5.511,
    5.82, 5.186, 5.186,
    7.357, 5.71, 6.921,
    6.921,
    5.507, 5.507, 5.71, 4.933,
    9.722, 9.722, 8.635,
    6.52, 5.748, 4.136,
    4.136,
    7.849, 7.337, 7.52
]


# --- create simple equally spaced x values ---
x1 = list(range(len(batches_phil_1)))
x2 = list(range(len(batches_phil_2)))
x3= list(range(len(batches_software_1)))
x4= list(range(len(batches_software_2)))
x5 = list(range(len(batches_all)))

plt.figure(figsize=(12, 5))

# Plot Set 1
plt.plot(x1, visc_phil_1, marker="o", color="#1f77b4", label="Phil's 1")
# Plot Set 2
plt.plot(x2, visc_phil_2, marker="o", color="#ff7f0e", label="Phil's 2")
plt.plot(x3, visc_software_1, marker="o", color="red", label="Software's 1")
plt.plot(x4, visc_software_2, marker="o", color="green", label="Software's 2")
plt.plot(x5, visc_all_batches, marker="o", color="black", label="All batches")
plt.ylabel("Viscosity (units)")
plt.xlabel("Sample index (equally spaced)")
plt.title("Viscosity — Two Sets (equally spaced x positions)")
plt.grid(True, linestyle="--", alpha=0.3)
plt.legend()

plt.tight_layout()
plt.show()