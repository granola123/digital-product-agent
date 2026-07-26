import sys, os
sys.path.insert(0, r"C:\Users\KimSh\.claude\skills\world-cuisine-meal-planner-pipeline\scripts")
import commons

q = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 8
for t in commons.search(q, limit):
    print(t)
