

def create_chat_workflow():
    model = create_agno_model()
    instructions_zh = dedent("""\
            你是一个中文聊天机器人。请和用户聊天。你只能说中文，不能说英文等其他语言。如果有数字，请说中文的数字。""")
    chat_agent = Agent(
        name='Chat Agent',
        role='Assistant',
        instructions=instructions_zh,
        model=model,
    )

    def chat_step(step_input):
        original_task = step_input.message or ''
        previous_steps = step_input.get_all_previous_content()
        print("original_task:", original_task)
        print("previous_steps:", previous_steps)

        text = previous_steps.split("===")[-1]
        text = text[1:]
        print("text:", text)
        if text.startswith("Timeout"):
            out_text = "Timeout"
            return StepOutput(content=f"{out_text}")
        response_stream = chat_agent.run(
            text, stream=True, stream_intermediate_steps=False,
        )

        speecher_start_event = threading.Event()
        speecher_stop_event = threading.Event()
        listener_stop_event = threading.Event()

        def stop_task():
            while True:
                time.sleep(1)
                while not speecher_start_event.is_set():
                    time.sleep(1)
                #text = "停止说话"
                text = ""
                input_dict = {"task": "speech_to_text_async", "lang": "zh", "text": text, "timeout": 10}
                print("可以停止说话了")
                run_response = stt_agent.run(
                    json.dumps(input_dict), stream=False, stream_intermediate_steps=False,
                )
                out_text = run_response.content
                print("收到命令：", out_text)
                if out_text.startswith("停止") or "停" in out_text:
                    speecher_stop_event.set()
                    break
                if listener_stop_event.is_set():
                    break

        speecher_stop_thread = threading.Thread(target=stop_task)
        speecher_stop_thread.start()

        out_text = ""
        num_setence = 0
        for event in response_stream:
            if event.event == "RunResponseContent":
                #print(f"Content: {event.content}")
                out_text += event.content
            elif event.event == "ToolCallStarted":
                print(f"Tool call started: {event.tool}")
            elif event.event == "ReasoningStep":
                print(f"Reasoning step: {event.content}")

            if speecher_stop_event.is_set():
                print("已经停止说话了")
                break

            #print(f"OutText: {out_text}")
            out_text = out_text
            if out_text.endswith("。") or out_text.endswith("？") or out_text.endswith("！") or \
                out_text.endswith("\n"):
                time.sleep(10)
                num_setence += 1
                input_dict = {"task": "text_to_speech", "lang": "zh", "text": out_text, "timeout": 30}
                print(input_dict)
                def sound_agent_run():
                    tts_agent.run(json.dumps(input_dict))
                speecher_start_event.set()
                threading.Thread(target=sound_agent_run).start()
                out_text = ""
                if num_setence > 3:
                    break

        #out_text = run_response.content
        out_text = ""
        #print(f"OutText: {out_text}")

        listener_stop_event.set()
        speecher_stop_thread.join()

        return StepOutput(content=f"{out_text}")
