import ollama

def main():
    response = ollama.chat(
        model="mistral:7b",
        messages=[{"role": "user", "content": "Hello, Ollama!"}]
    )
    print(response["message"]["content"])       