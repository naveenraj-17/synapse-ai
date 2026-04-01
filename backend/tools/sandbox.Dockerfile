FROM python:3.12-slim

RUN pip install --no-cache-dir --disable-pip-version-check \
    pandas \
    pandas_ta \
    numpy \
    scipy \
    scikit-learn \
    matplotlib \
    seaborn \
    requests \
    httpx \
    beautifulsoup4 \
    lxml \
    openpyxl \
    xlsxwriter \
    pyyaml \
    python-dateutil \
    pytz \
    tabulate \
    jinja2 \
    jsonschema \
    pillow \
    sympy
