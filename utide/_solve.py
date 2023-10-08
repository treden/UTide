"""
Central module for calculating the tidal amplitudes, phases, etc.
"""
import numpy as np

from ._time_conversion import _normalize_time
from .confidence import _confidence
from .constituent_selection import ut_cnstitsel
from .diagnostics import _PE, _SNR, ut_diagn
from .ellipse_params import ut_cs2cep
from .harmonics import ut_E
from .robustfit import robustfit
from .utilities import Bunch

default_opts = {
    "constit": "auto",
    "order_constit": None,
    "conf_int": "linear",
    "method": "ols",
    "trend": True,
    "phase": "Greenwich",
    "nodal": True,
    "infer": None,
    "MC_n": 200,
    "Rayleigh_min": 1,
    "robust_kw": {"weight_function": "cauchy"},
    "white": False,
    "verbose": True,
    "epoch": None,
}


def _process_opts(opts, is_2D):
    newopts = Bunch(default_opts)
    newopts.update_values(strict=True, **opts)
    # TODO: add more validations.
    newopts.infer = validate_infer(newopts.infer, is_2D)
    snr = newopts.conf_int != "none"
    newopts.order_constit = validate_order_constit(newopts.order_constit, snr)

    compat_opts = _translate_opts(newopts)

    return compat_opts


def _translate_opts(opts):
    # Temporary shim between new-style options and Matlab heritage.
    # Here or elsewhere, proper validation remains to be added.
    oldopts = Bunch()
    oldopts.cnstit = opts.constit
    oldopts.ordercnstit = opts.order_constit
    oldopts.infer = opts.infer  # we will not use the matlab names, though

    oldopts.conf_int = True
    if opts.conf_int == "linear":
        oldopts.linci = True
    elif opts.conf_int == "MC":
        oldopts.linci = False
    elif opts.conf_int == "none":
        oldopts.conf_int = False
        oldopts.nodiagn = 1
    else:
        raise ValueError("'conf_int' must be 'linear', 'MC', or 'none'")

    oldopts.notrend = not opts.trend
    oldopts["nodesatlint"] = False
    oldopts["nodesatnone"] = False
    oldopts["gwchlint"] = False
    oldopts["gwchnone"] = False
    if opts.nodal == "linear_time":
        oldopts["nodsatlint"] = True
    elif not opts.nodal:
        oldopts["nodsatnone"] = True
    if opts.phase == "linear_time":
        oldopts["gwchlint"] = True
    elif opts.phase == "raw":
        oldopts["gwchnone"] = True
    # Otherwise it should be default, 'Greenwich.'
    oldopts.rmin = opts.Rayleigh_min
    oldopts.white = opts.white
    oldopts.newopts = opts  # So we can access new opts via the single "opt."
    oldopts["RunTimeDisp"] = opts.verbose
    oldopts.epoch = opts.epoch
    return oldopts


def validate_infer(infer, is_2D):
    if infer is None or infer == "none":
        return None
    required_keys = {"inferred_names", "reference_names", "amp_ratios", "phase_offsets"}
    keys = set(infer.keys())
    if keys < required_keys:
        raise ValueError("infer option must include %s" % required_keys)
    nI = len(infer.inferred_names)
    if len(infer.reference_names) != nI:
        raise ValueError("inferred_names must be same" "  length as reference_names")
    nratios = 2 * nI if is_2D else nI
    if len(infer.amp_ratios) != nratios or len(infer.phase_offsets) != nratios:
        raise ValueError("ratios and offsets need to have length %d" % nratios)
    if "approximate" not in infer:
        infer.approximate = False
    return infer


def validate_order_constit(arg, have_snr):
    available = ["PE", "frequency"]
    if have_snr:
        available.append("SNR")
    if arg is None:
        return "PE"
    if isinstance(arg, str) and arg in available:
        return arg
    if not isinstance(arg, str) and np.iterable(arg):
        return arg  # TODO: add checking of its elements
    raise ValueError(
        f"order_constit must be one of {available} or"
        f" a sequence of constituents, not '{arg}'",
    )


def solve(t, u, v=None, lat=None, solve = '1D', **opts):
    """
    Calculate amplitude, phase, confidence intervals of tidal constituents.

    Parameters
    ----------
    t : array_like
        Time in days since `epoch`, or np.datetime64 array, or pandas datetime array.
    u : array_like
        Sea-surface height, velocity component, etc.
    v : {None, array_like}, optional
        If `u` is a velocity component, `v` is the orthogonal component.
    lat : float, required
        Latitude in degrees.
    epoch : {string, `datetime.date`, `datetime.datetime`}, if datenum is provided in t.
        Default `None` if `t` is `datetime`, `np.datetime64`, or `pd.datetime array.`
        Optional valid strings are
            - 'python' : if `t` is days since '0000-12-31'
            - 'matlab' : if `t` is days since '0000-00-00'
        Or, an arbitrary date in the form 'YYYY-MM-DD'.
    constit : {'auto', sequence}, optional
        List of strings with standard letter abbreviations of
        tidal constituents; or 'auto' to let the list be determined
        based on the time span.
    conf_int : {'linear', 'MC', 'none'}, optional
        If not 'none' (string), calculate linearized confidence
        intervals, or use a Monte-Carlo simulation.
    method : {'ols', 'robust'}, optional
        Solve with ordinary least squares, or with a robust algorithm.
    trend : bool, optional
        True (default) to include a linear trend in the model.
    phase : {'Greenwich', 'linear_time', 'raw'}, optional
        Give Greenwich-referenced phase lags, an approximation
        using linearized times, or raw lags.
    nodal : {True, False, 'linear_time'}, optional
        True (default) to include nodal/satellite corrections;
        'linear_time' to use the linearized time approximation;
        False to omit nodal corrections.

    Returns
    -------
    coef : Bunch
        Data container with all configuration and solution information:

    Other Parameters
    ----------------
    infer : {None, dict or Bunch}, optional; default is None.
        If not None, the items are:

        **inferred_names** : {sequence of N strings}
            inferred constituent names
        **reference_names** : {sequence of N strings}
            reference constituent names
        **amp_ratios** : {sequence, N or 2N floats}
            amplitude ratios (unitless)
        **phase_offsets** : {sequence, N or 2N floats}
            phase offsets (degrees)
        **approximate** : {bool, optional (default is False)}
            use approximate method

        amp_ratios and phase_offsets have length N for a scalar
        time series, or 2N for a vector series.

    order_constit : {'PE', 'SNR', 'frequency', sequence}, optional
        The default is 'PE' (percent energy) order, returning results ordered from
        high energy to low.
        The 'SNR' order is from high signal-to-noise ratio to low, and is
        available only if `conf_int` is not 'none'. The
        'frequency' order is from low to high frequency. Alternatively, a
        sequence of constituent names may be supplied, typically the same list as
        given in the *constit* option.
    MC_n : integer, optional
        Not yet implemented.
    robust_kw : dict, optional
        Keyword arguments for `robustfit`, if `method` is 'robust'.
    Rayleigh_min : float
        Minimum conventional Rayleigh criterion for automatic
        constituent selection; default is 1.
    white : bool
        If False (default), use band-averaged spectra from the
        residuals in the confidence limit estimates; if True,
        assume a white background spectrum.
    verbose : {True, False}, optional
        True (default) turns on verbose output. False emits no messages.

    Note
    ----
    `utide.reconstruct` requires the calculation of confidence intervals.

    Notes
    -----

    To be added: much additional explanation.

    There will also be more "Other Parameters".

    """

    compat_opts = _process_opts(opts, v is not None)

    # TODO: Proper transparent management of the 1D and 2D case with appropriates input's tests 
    if solve == '1D':
        coef = _solv1(t, u, v, lat, **compat_opts)
    elif solve == '2D':
        coef = _solv2(t, u, v, lat, **compat_opts)

    return coef


def _solv1(tin, uin, vin, lat, **opts):
    # The following returns a possibly modified copy of tin (ndarray).
    # t, u, v are fully edited ndarrays (unless v is None).
    packed = _slvinit(tin, uin, vin, lat, **opts)
    tin, t, u, v, tref, lor, elor, opt = packed
    nt = len(t)
    # if opt["RunTimeDisp"]:
    #     print("solve: ", end="")

    # opt['cnstit'] = cnstit
    cnstit, coef = ut_cnstitsel(
        tref,
        opt["rmin"] / (24 * lor),
        opt["cnstit"],
        opt["infer"],
    )

    # a function we don't need
    # coef.aux.rundescr = ut_rundescr(opt,nNR,nR,nI,t,tgd,uvgd,lat)

    coef.aux.opt = opt
    coef.aux.lat = lat

    # if opt["RunTimeDisp"]:
    #     print("matrix prep ... ", end="")

    ngflgs = [opt["nodsatlint"], opt["nodsatnone"], opt["gwchlint"], opt["gwchnone"]]

    E_args = (lat, ngflgs, opt.prefilt)

    # Make the model array, starting with the harmonics.
    E = ut_E(t, tref, cnstit.NR.frq, cnstit.NR.lind, *E_args)

    # Positive and negative frequencies
    B = np.hstack((E, E.conj()))

    if opt.infer is not None:
        Etilp = np.empty((nt, coef.nR), dtype=complex)
        Etilm = np.empty((nt, coef.nR), dtype=complex)

        if not opt.infer.approximate:
            for k, ref in enumerate(cnstit.R):
                E = ut_E(t, tref, ref.frq, ref.lind, *E_args)
                # (nt,1)
                Q = ut_E(t, tref, ref.I.frq, ref.I.lind, *E_args) / E
                # (nt,ni)
                Qsum_p = (Q * ref.I.Rp).sum(axis=1)
                Etilp[:, k] = E[:, 0] * (1 + Qsum_p)
                Qsum_m = (Q * np.conj(ref.I.Rm)).sum(axis=1)
                Etilm[:, k] = E[:, 0] * (1 + Qsum_m)

        else:
            # Approximate inference.
            Q = np.empty((coef.nR,), dtype=float)
            beta = np.empty((coef.nR,), dtype=float)

            for k, ref in enumerate(cnstit.R):
                E = ut_E(t, tref, ref.frq, ref.lind, *E_args)[:, 0]
                Etilp[:, k] = E
                Etilm[:, k] = E
                num = ut_E(tref, tref, ref.I.frq, ref.I.lind, *E_args).real
                den = ut_E(tref, tref, ref.frq, ref.lind, *E_args).real
                Q[k] = (num / den)[0, 0]
                arg = np.pi * lor * 24 * (ref.I.frq - ref.frq) * (nt + 1) / nt
                beta[k] = np.sin(arg) / arg

        B = np.hstack((B, Etilp, np.conj(Etilm)))

    # add the mean
    B = np.hstack((B, np.ones((nt, 1))))

    if not opt["notrend"]:
        B = np.hstack((B, ((t - tref) / lor)[:, np.newaxis]))

    # nm = B.shape[1]  # 2*(nNR + nR) + 1, plus 1 if trend is included.

    # if opt["RunTimeDisp"]:
    #     print("solution ... ", end="")

    if opt["twodim"]:
        xraw = u + 1j * v
    else:
        xraw = u

    if opt.newopts.method == "ols":
        # Model coefficients.
        try:
            m = np.linalg.lstsq(B, xraw, rcond=None)[0]
        except TypeError:
            m = np.linalg.lstsq(B, xraw)[0]
        W = np.ones(nt)  # Uniform weighting; we could use a scalar 1, or None.
    else:
        rf = robustfit(B, xraw, **opt.newopts.robust_kw)
        m = rf.b
        W = rf.w
        coef.rf = rf
    coef.weights = W

    xmod = np.dot(B, m)  # Model fit.

    if not opt["twodim"]:
        xmod = np.real(xmod)

    e = W * (xraw - xmod)  # Weighted residuals.

    nI, nR, nNR = coef.nI, coef.nR, coef.nNR

    ap = np.hstack((m[:nNR], m[2 * nNR : 2 * nNR + nR]))
    i0 = 2 * nNR + nR
    am = np.hstack((m[nNR : 2 * nNR], m[i0 : i0 + nR]))

    Xu = np.real(ap + am)
    Yu = -np.imag(ap - am)

    if not opt["twodim"]:
        coef["A"], _, _, coef["g"] = ut_cs2cep(Xu, Yu)
        Xv = []
        Yv = []

    else:
        Xv = np.imag(ap + am)
        Yv = np.real(ap - am)
        packed = ut_cs2cep(Xu, Yu, Xv, Yv)
        coef["Lsmaj"], coef["Lsmin"], coef["theta"], coef["g"] = packed

    # Mean and trend.
    if opt["twodim"]:
        if opt["notrend"]:
            coef["umean"] = np.real(m[-1])
            coef["vmean"] = np.imag(m[-1])
        else:
            coef["umean"] = np.real(m[-2])
            coef["vmean"] = np.imag(m[-2])
            coef["uslope"] = np.real(m[-1]) / lor
            coef["vslope"] = np.imag(m[-1]) / lor
    else:
        if opt["notrend"]:
            coef["mean"] = np.real(m[-1])
        else:
            coef["mean"] = np.real(m[-2])
            coef["slope"] = np.real(m[-1]) / lor

    if opt.infer:
        # complex coefficients
        apI = np.empty((nI,), dtype=complex)
        amI = np.empty((nI,), dtype=complex)
        ind = 0

        for k, ref in enumerate(cnstit.R):
            apI[ind : ind + ref.nI] = ref.I.Rp * ap[nNR + k]
            amI[ind : ind + ref.nI] = ref.I.Rm * am[nNR + k]
            ind += ref.nI

        XuI = (apI + amI).real
        YuI = -(apI - amI).imag

        if not opt.twodim:
            A, _, _, g = ut_cs2cep(XuI, YuI)
            coef.A = np.hstack((coef.A, A))
            coef.g = np.hstack((coef.g, g))
        else:
            XvI = (apI + amI).imag
            YvI = (apI - amI).real
            Lsmaj, Lsmin, theta, g = ut_cs2cep(XuI, YuI, XvI, YvI)
            coef.Lsmaj = np.hstack((coef.Lsmaj, Lsmaj))
            coef.Lsmin = np.hstack((coef.Lsmin, Lsmin))
            coef.theta = np.hstack((coef.theta, theta))
            coef.g = np.hstack((coef.g, g))

    if opt["conf_int"]:
        coef = _confidence(
            coef,
            cnstit,
            opt,
            t,
            e,
            tin,
            elor,
            xraw,
            xmod,
            W,
            m,
            B,
            Xu,
            Yu,
            Xv,
            Yv,
        )

    # Diagnostics.
    if not opt["nodiagn"]:
        coef = ut_diagn(coef)
        # Adds a diagn dictionary, always sorted by energy.
        # This doesn't seem very useful.  Let's directly add the variables
        # to the base coef structure.  Then they can be sorted with everything
        # else.
        coef["PE"] = _PE(coef)
        coef["SNR"] = _SNR(coef)

    # Re-order constituents.
    coef = _reorder(coef, opt)
    # This might have added PE if it was not already present.

    # if opt["RunTimeDisp"]:
    #     print("done.")

    return coef

def _solv2(tin, uin, vin, lat, **opts):
    # The following returns a possibly modified copy of tin (ndarray).
    # t, u, v are fully edited ndarrays (unless v is None).
    packed = _slvinit(tin, uin, vin, lat, **opts)
    tin, t, u, v, tref, lor, elor, opt = packed
    nt = len(t)

    # TODO: Put back the display option 
    # if opt["RunTimeDisp"]:
    #     print("solve: ", end="")

    # opt['cnstit'] = cnstit
    cnstit, coef = ut_cnstitsel(
        tref,
        opt["rmin"] / (24 * lor),
        opt["cnstit"],
        opt["infer"],
    )

    # a function we don't need
    # coef.aux.rundescr = ut_rundescr(opt,nNR,nR,nI,t,tgd,uvgd,lat)

    coef.aux.opt = opt
    coef.aux.lat = lat

    # if opt["RunTimeDisp"]:
    #     print("matrix prep ... ", end="")

    ngflgs = [opt["nodsatlint"], opt["nodsatnone"], opt["gwchlint"], opt["gwchnone"]]

    E_args = (lat, ngflgs, opt.prefilt)

    # Make the model array, starting with the harmonics.
    E = ut_E(t, tref, cnstit.NR.frq, cnstit.NR.lind, *E_args)

    # Positive and negative frequencies
    B = np.hstack((E, E.conj()))

    # TODO: Test/fix the 2D case with inference
    if opt.infer is not None:
        Etilp = np.empty((nt, coef.nR), dtype=complex)
        Etilm = np.empty((nt, coef.nR), dtype=complex)

        if not opt.infer.approximate:
            for k, ref in enumerate(cnstit.R):
                E = ut_E(t, tref, ref.frq, ref.lind, *E_args)
                # (nt,1)
                Q = ut_E(t, tref, ref.I.frq, ref.I.lind, *E_args) / E
                # (nt,ni)
                Qsum_p = (Q * ref.I.Rp).sum(axis=1)
                Etilp[:, k] = E[:, 0] * (1 + Qsum_p)
                Qsum_m = (Q * np.conj(ref.I.Rm)).sum(axis=1)
                Etilm[:, k] = E[:, 0] * (1 + Qsum_m)

        else:
            # Approximate inference.
            Q = np.empty((coef.nR,), dtype=float)
            beta = np.empty((coef.nR,), dtype=float)

            for k, ref in enumerate(cnstit.R):
                E = ut_E(t, tref, ref.frq, ref.lind, *E_args)[:, 0]
                Etilp[:, k] = E
                Etilm[:, k] = E
                num = ut_E(tref, tref, ref.I.frq, ref.I.lind, *E_args).real
                den = ut_E(tref, tref, ref.frq, ref.lind, *E_args).real
                Q[k] = (num / den)[0, 0]
                arg = np.pi * lor * 24 * (ref.I.frq - ref.frq) * (nt + 1) / nt
                beta[k] = np.sin(arg) / arg

        B = np.hstack((B, Etilp, np.conj(Etilm)))

    # add the mean
    B = np.hstack((B, np.ones((nt, 1))))

    if not opt["notrend"]:
        B = np.hstack((B, ((t - tref) / lor)[:, np.newaxis]))

    # nm = B.shape[1]  # 2*(nNR + nR) + 1, plus 1 if trend is included.

    # if opt["RunTimeDisp"]:
    #     print("solution ... ", end="")

    if opt["twodim"]:
        xraw = u + 1j * v
    else:
        xraw = u

    if opt.newopts.method == "ols":
        # Model coefficients.
        try:
            m = np.linalg.lstsq(B, xraw.T, rcond=None)[0]
        except TypeError:
            m = np.linalg.lstsq(B, xraw.T)[0]
        W = np.ones(nt)  # Uniform weighting; we could use a scalar 1, or None.

    # Utide2D : The robust fit is not handled (for now?)
    # else:
    #     rf = robustfit(B, xraw, **opt.newopts.robust_kw)
    #     m = rf.b
    #     W = rf.w
    #     coef.rf = rf
    coef.weights = W

    xmod = np.dot(B, m).T  # Model fit.

    if not opt["twodim"]:
        xmod = np.real(xmod)

    e = W * (xraw - xmod)  # Weighted residuals.

    nI, nR, nNR = coef.nI, coef.nR, coef.nNR

    ap = np.hstack((m[:nNR].T, m[2 * nNR : 2 * nNR + nR].T)).T
    i0 = 2 * nNR + nR
    am = np.hstack((m[nNR : 2 * nNR].T, m[i0 : i0 + nR].T)).T

    Xu = np.real(ap + am)
    Yu = -np.imag(ap - am)

    if not opt["twodim"]:
        coef["A"], _, _, coef["g"] = ut_cs2cep(Xu, Yu)
        Xv = []
        Yv = []

    else:
        Xv = np.imag(ap + am)
        Yv = np.real(ap - am)
        packed = ut_cs2cep(Xu, Yu, Xv, Yv)
        coef["Lsmaj"], coef["Lsmin"], coef["theta"], coef["g"] = packed

    # Mean and trend.
    if opt["twodim"]:
        if opt["notrend"]:
            coef["umean"] = np.real(m[-1])
            coef["vmean"] = np.imag(m[-1])
        else:
            coef["umean"] = np.real(m[-2])
            coef["vmean"] = np.imag(m[-2])
            coef["uslope"] = np.real(m[-1]) / lor
            coef["vslope"] = np.imag(m[-1]) / lor
    else:
        if opt["notrend"]:
            coef["mean"] = np.real(m[-1])
        else:
            coef["mean"] = np.real(m[-2])
            coef["slope"] = np.real(m[-1]) / lor

    if opt.infer:
        # complex coefficients
        apI = np.empty((nI,), dtype=complex)
        amI = np.empty((nI,), dtype=complex)
        ind = 0

        for k, ref in enumerate(cnstit.R):
            apI[ind : ind + ref.nI] = ref.I.Rp * ap[nNR + k]
            amI[ind : ind + ref.nI] = ref.I.Rm * am[nNR + k]
            ind += ref.nI

        XuI = (apI + amI).real
        YuI = -(apI - amI).imag

        if not opt.twodim:
            A, _, _, g = ut_cs2cep(XuI, YuI)
            coef.A = np.hstack((coef.A, A))
            coef.g = np.hstack((coef.g, g))
        else:
            XvI = (apI + amI).imag
            YvI = (apI - amI).real
            Lsmaj, Lsmin, theta, g = ut_cs2cep(XuI, YuI, XvI, YvI)
            coef.Lsmaj = np.hstack((coef.Lsmaj, Lsmaj))
            coef.Lsmin = np.hstack((coef.Lsmin, Lsmin))
            coef.theta = np.hstack((coef.theta, theta))
            coef.g = np.hstack((coef.g, g))

    # TODO: 2D OLS Confidence intervals
    # if opt["conf_int"]:
    #     coef = _confidence(
    #         coef,
    #         cnstit,
    #         opt,
    #         t,
    #         e,
    #         tin,
    #         elor,
    #         xraw,
    #         xmod,
    #         W,
    #         m,
    #         B,
    #         Xu,
    #         Yu,
    #         Xv,
    #         Yv,
    #     )

    # Diagnostics.
    # TODO: 2D Diagnostics 
    # if not opt["nodiagn"]:
    #     coef = ut_diagn(coef)
    #     # Adds a diagn dictionary, always sorted by energy.
    #     # This doesn't seem very useful.  Let's directly add the variables
    #     # to the base coef structure.  Then they can be sorted with everything
    #     # else.
    #     coef["PE"] = _PE(coef)
    #     coef["SNR"] = _SNR(coef)

    # Re-order constituents.
    # TODO: 2D Reordering 
    # coef = _reorder(coef, opt)
    # This might have added PE if it was not already present.

    # if opt["RunTimeDisp"]:
    #     print("done.")

    return coef


def _reorder(coef, opt):
    if opt["ordercnstit"] == "PE":
        # Default: order by decreasing energy.
        if "PE" not in coef:
            coef["PE"] = _PE(coef)
        ind = coef["PE"].argsort()[::-1]

    elif opt["ordercnstit"] == "frequency":
        ind = coef["aux"]["frq"].argsort()

    elif opt["ordercnstit"] == "SNR":
        # If we are here, we should be guaranteed to have SNR already.
        ind = coef["SNR"].argsort()[::-1]
    else:
        namelist = list(coef["name"])
        ilist = [namelist.index(name) for name in opt["ordercnstit"]]
        ind = np.array(ilist, dtype=int)

    arrays = "name PE SNR A A_ci g g_ci Lsmaj Lsmaj_ci Lsmin Lsmin_ci theta theta_ci"
    reorderlist = [a for a in arrays.split() if a in coef]

    for key in reorderlist:
        coef[key] = coef[key][ind]

    coef["aux"]["frq"] = coef["aux"]["frq"][ind]
    coef["aux"]["lind"] = coef["aux"]["lind"][ind]
    return coef


def _slvinit(tin, uin, vin, lat, **opts):
    if lat is None:
        raise ValueError("Latitude must be supplied")

    # UTide2D : Remove the check for 1D u values (t must be still 1D)
    # TODO: Check the shape of u (2D cpmsistent with the len of t vector)
    # TODO: manage the v value for 2D currents
    # TODO: Verify that the t vector is the same len of first u dim
    
    # if tin.shape != uin.shape or tin.ndim != 1 or uin.ndim != 1:
    #     raise ValueError("t and u must be 1-D arrays")

    if tin.ndim != 1:
        raise ValueError("t must be 1-D array")

    if vin is not None and vin.shape != uin.shape:
        raise ValueError("v must have the same shape as u")

    opt = Bunch(twodim=(vin is not None))

    # Step 0: apply epoch to time.
    tin = _normalize_time(tin, opts["epoch"])

    # Step 1: remove invalid times from tin, uin, vin
    tin = np.ma.masked_invalid(tin)
    uin = np.ma.masked_invalid(uin)
    if vin is not None:
        vin = np.ma.masked_invalid(vin)
    if np.ma.is_masked(tin):
        goodmask = ~np.ma.getmaskarray(tin)
        uin = uin.compress(goodmask)
        if vin is not None:
            vin = vin.compress(goodmask)

    tin = tin.compressed()  # No longer masked.

    # Step 2: generate t, u, v from edited tin, uin, vin.
    v = None
    if np.ma.is_masked(uin) or np.ma.is_masked(vin):
        mask = np.ma.getmaskarray(uin)
        if vin is not None:
            mask = np.ma.mask_or(np.ma.getmaskarray(vin), mask)
        goodmask = ~mask
        t = tin.compress(goodmask)
        u = uin.compress(goodmask).filled()
        if vin is not None:
            v = vin.compress(goodmask).filled()
    else:
        t = tin
        u = uin.filled()
        if vin is not None:
            v = vin.filled()

    # Now t, u, v, tin are clean ndarrays; uin and vin are masked,
    # but don't necessarily have masked values.

    # Are the times equally spaced?
    eps = np.finfo(np.float64).eps
    if np.var(np.unique(np.diff(tin))) < eps:
        opt["equi"] = True  # based on times; u/v can still have nans ("gappy")
        lor = np.ptp(tin)
        ntgood = len(tin)
        elor = lor * ntgood / (ntgood - 1)
        tref = 0.5 * (tin[0] + tin[-1])
    else:
        opt["equi"] = False
        lor = np.ptp(t)
        nt = len(t)
        elor = lor * nt / (nt - 1)
        tref = 0.5 * (t[0] + t[-1])

    # Options.
    opt["conf_int"] = True
    opt["cnstit"] = "auto"
    opt["notrend"] = 0
    opt["prefilt"] = []
    opt["nodsatlint"] = 0
    opt["nodsatnone"] = 0
    opt["gwchlint"] = 0
    opt["gwchnone"] = 0
    opt["infer"] = None
    opt["inferaprx"] = 0
    opt["rmin"] = 1
    opt["method"] = "ols"
    opt["tunrdn"] = 1
    opt["linci"] = False
    opt["white"] = 0
    opt["nrlzn"] = 200
    opt["lsfrqosmp"] = 1
    opt["nodiagn"] = 0
    opt["diagnplots"] = 0
    opt["diagnminsnr"] = 2
    opt["ordercnstit"] = None
    opt["runtimedisp"] = "yyy"

    # Update the default opt dictionary with the kwargs,
    # ensuring that every kwarg key matches a key in opt.
    for key, item in opts.items():
        try:
            opt[key] = item
        except KeyError:
            print(f"solve: unrecognized input: {key}")

    return tin, t, u, v, tref, lor, elor, opt
