def pytest_addoption(parser):
    parser.addoption(
        "--update-golden",
        action="store_true",
        default=False,
        help="re-bless golden simulation snapshots instead of asserting against them",
    )
