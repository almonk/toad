import click
from toad.app import ToadApp


@click.command()
def main():
    """Toad. The Batrachian AI."""

    app = ToadApp()
    app.run()


if __name__ == "__main__":
    main()
