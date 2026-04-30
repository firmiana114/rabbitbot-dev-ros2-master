
def process_text_en_for_stt(text):
    # Strip left spaces.
    text = text.lstrip()
    if len(text) == 0:
        return None
    # Start from the 1st alpha.
    i = 0
    while not text[i].isalpha():
        i += 1
        if i >= len(text):
            return None
    text = text[i:]
    # Remove "." and "?".
    if text.endswith(".") or text.endswith("?"):
        text = text[:-1]
    elif text.endswith(".\n") or text.endswith("?\n"):
        text = text[:-2]
    # Remove "\""
    text = text.replace("\"", "")
    return text


def process_text_zh_for_stt(text):
    text = text.lstrip()

    text = text.replace("**", "")
    text = text.replace("- ", "")
    text = text.replace("：", "")
    text = text.replace("。", "")

    return text
