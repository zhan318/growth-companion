from agent.agent import Agent


def main():
    print("AI助手启动成功！输入 exit 退出\n")

    agent = Agent()

    while True:
        user_input = input("你: ")

        if user_input.lower() == "exit":
            print("AI: 再见！")
            break

        if not user_input.strip():
            continue

        answer = agent.run(user_input)

        print("AI:", answer)


if __name__ == "__main__":
    main()
