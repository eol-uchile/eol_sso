import setuptools

setuptools.setup(
    name="eol_sso",
    version="1.0.0",
    author="EOL Uchile",
    author_email="eol-ing@uchile.cl",
    description="Middleware between apps and uchileedxlogin/eol_sso_login",
    long_description="Middleware between apps and uchileedxlogin/eol_sso_login",
    url="https://github/eol-uchile/eol_sso",
    packages=setuptools.find_packages(),
    install_requires=[],
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    entry_points={
        "lms.djangoapp": ["eol_sso = eol_sso.apps:EolSsoConfig"],
        "cms.djangoapp": ["eol_sso = eol_sso.apps:EolSsoConfig"]
    },
)
