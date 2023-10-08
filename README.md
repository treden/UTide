# UTide

[![gha](https://github.com/wesleybowman/UTide/actions/workflows/tests.yml/badge.svg)](https://github.com/wesleybowman/UTide/actions)
[![license](https://anaconda.org/conda-forge/utide/badges/license.svg)](https://choosealicense.com/licenses/mit/)
[![downloads](https://anaconda.org/conda-forge/utide/badges/downloads.svg)](https://anaconda.org/conda-forge/utide)
[![anaconda_cloud](https://anaconda.org/conda-forge/utide/badges/version.svg)](https://anaconda.org/conda-forge/utide)

Python re-implementation of the Matlab package UTide.

Still in heavy development\--everything is subject to change!

#### Fork development version : Small adaptations to 1D solver (OLS only), reconstruction routine and Bunch objects to support 2D inputs in a vectorized approach. The objective is to make the changes transparents for the user, in order to keep an identical usage and syntax with the original library using 1D or 2D inputs. The development is motivated by the need to process tide from 2D model outputs, SWOT observations or other groups of timeseries in a efficient way, while keeping profit of the versatile approach and optimisations implemented in the UTide library. 
Contact : Y.T. Tranchant, yanntreden.tranchant@utas.edu.au

Note: the user interface differs from the Matlab version, so consult the
Python function docstrings to see how to specify parameters. Some
functionality from the Matlab version is not yet available. For more
information see:

    Codiga, D.L., 2011. Unified Tidal Analysis and Prediction Using the
    UTide Matlab Functions. Technical Report 2011-01. Graduate School
    of Oceanography, University of Rhode Island, Narragansett, RI.
    59pp.
    ftp://www.po.gso.uri.edu/pub/downloads/codiga/pubs/2011Codiga-UTide-Report.pdf

    UTide v1p0 9/2011 d.codiga@gso.uri.edu
    http://www.po.gso.uri.edu/~codiga/utide/utide.htm

# Installation

``` shell
pip install -e git+git://github.com/treden/UTide.git@master#egg=utide
```

If you are using conda (not yet),

``` shell
conda install utide --channel conda-forge
```

The public functions can be imported using

``` python
from utide import solve, reconstruct
```

A sample call would be

``` python
from utide import solve

coef = solve(
    time,
    time_series_u,
    time_series_v,
    lat=30,
    nodal=False,
    trend=False,
    method="ols",
    conf_int="linear",
    Rayleigh_min=0.95,
)
```

For more examples see the
[notebooks](https://nbviewer.jupyter.org/github/wesleybowman/UTide/tree/master/notebooks/)
folder.
