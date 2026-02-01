from cryptography.fernet import Fernet


def main() -> None:
    key = Fernet.generate_key().decode("utf-8")
    print(key)


if __name__ == "__main__":
    main()
