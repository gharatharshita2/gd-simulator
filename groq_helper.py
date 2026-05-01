from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def get_ai_discussion(user_input, topic, difficulty="Medium"):

    difficulty_rules = {
        "Easy": """
DIFFICULTY: EASY
- This is a beginner level evaluation
- Reward basic answers generously
- A simple 2-3 sentence answer with one point = 6-7
- A good answer with one example = 7-8
- An excellent answer with structure = 8-9
- Only give below 4 if the answer is one word or completely off topic
- Be encouraging and supportive in feedback
""",
        "Medium": """
DIFFICULTY: MEDIUM
- This is an intermediate level evaluation
- A basic 2-3 sentence answer = 4-5
- An answer with examples but no structure = 5-6
- A well structured answer with examples = 7-8
- An outstanding answer with data and counterarguments = 9-10
- Be honest and direct in feedback
""",
        "Hard": """
DIFFICULTY: HARD
- This is an advanced level evaluation — treat this like a final placement round
- A basic answer with no examples = 2-3
- An answer with examples but no data or structure = 3-5
- A well structured answer with examples = 5-6
- An answer with data, examples and counterarguments = 7-8
- Only give 9-10 for truly exceptional answers with statistics, policy knowledge and strong delivery
- Be very strict and critical in feedback like a senior interviewer
"""
    }

    rules = difficulty_rules.get(difficulty, difficulty_rules["Medium"])

    prompt = f"""
You are a strict and honest GD (Group Discussion) evaluator and simulator.

Topic: {topic}
User's response: "{user_input}"

{rules}

GLOBAL SCORING RULES:
- One word or one line answers → all scores below 3 regardless of difficulty
- Never give the same score for Easy and Hard — there must be a clear difference
- Scores must reflect the difficulty level strictly
- Easy scores will naturally be higher than Hard scores for the same answer

Now respond as three GD participants:

Confident Speaker:
(React to what the user said, give a confident 2 line opinion based on difficulty level)

Aggressive Debater:
(Challenge the user — be mild on Easy, aggressive on Hard)

Logical Thinker:
(Give a balanced 2 line view — simple on Easy, deeply analytical on Hard)

Then give feedback:

FEEDBACK_START
Strengths: (what was good — be encouraging on Easy, strict on Hard)
Weaknesses: (what was missing — be gentle on Easy, harsh on Hard)
Suggestions: (what to add — basic tips on Easy, advanced tips on Hard)
SCORES:
clarity: (1-10)
logic: (1-10)
confidence: (1-10)
relevance: (1-10)
FEEDBACK_END
"""
    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": f"You are a GD evaluator. Difficulty is {difficulty}. Easy = generous scoring. Medium = balanced scoring. Hard = very strict scoring. The SAME answer must score significantly differently across difficulty levels. Easy should score 2-3 points higher than Hard for the same answer."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.3
        )
        return response.choices[0].message.content
    except Exception as e:
        return f"Error: {e}"


def parse_scores(ai_output):
    scores = {"clarity": 5, "logic": 5, "confidence": 5, "relevance": 5}
    try:
        for key in scores:
            for line in ai_output.split("\n"):
                if line.strip().lower().startswith(key + ":"):
                    val = line.split(":")[1].strip().split()[0]
                    scores[key] = float(val)
    except:
        pass
    scores["overall"] = round(sum(scores.values()) / 4, 1)
    return scores