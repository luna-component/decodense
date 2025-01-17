#!/usr/bin/env python
# -*- coding: utf-8 -*

"""
main mf_decomp program
"""

__author__ = 'Dr. Janus Juul Eriksen, University of Bristol, UK'
__maintainer__ = 'Dr. Janus Juul Eriksen'
__email__ = 'janus.eriksen@bristol.ac.uk'
__status__ = 'Development'

import numpy as np
from pyscf import gto, scf, dft
from typing import Dict, Tuple, List, Union, Optional, Any

from .decomp import DecompCls, sanity_check
from .orbitals import loc_orbs, assign_rdm1s
from .properties import prop_tot
from .tools import make_natorb, mf_info, write_rdm1


def main(mol: gto.Mole, decomp: DecompCls, \
         mf: Union[scf.hf.SCF, dft.rks.KohnShamDFT], \
         rdm1_orb: np.ndarray = None, \
         rdm1_eff: np.ndarray = None, \
         loc_lst: Optional[Any] = None) -> Dict[str, Any]:
        """
        main decodense program
        """
        # sanity check
        sanity_check(mol, decomp)

        # format orbitals from mean-field calculation
        if rdm1_orb is None:
            mo_coeff, mo_occ = mf_info(mf)
        else:
            mo_coeff, mo_occ = make_natorb(mol, np.asarray(mf.mo_coeff), np.asarray(rdm1_orb))

        # compute localized molecular orbitals
        if decomp.loc != '':
            mo_coeff = loc_orbs(mol, mo_coeff, mo_occ, decomp.loc, decomp.ndo, loc_lst)

        # decompose property
        if decomp.part in ['atoms', 'eda']:
            # compute population weights
            weights = assign_rdm1s(mol, mo_coeff, mo_occ, decomp.pop, decomp.part, \
                                   decomp.ndo, decomp.multiproc, decomp.verbose)
            # compute decomposed results
            decomp.res = prop_tot(mol, mf, mo_coeff, mo_occ, rdm1_eff, \
                                  decomp.pop, decomp.prop, decomp.part, \
                                  decomp.ndo, decomp.multiproc, decomp.gauge_origin, \
                                  weights = weights)
        else: # orbs
            # compute decomposed results
            decomp.res = prop_tot(mol, mf, mo_coeff, mo_occ, rdm1_eff, \
                                  decomp.pop, decomp.prop, decomp.part, \
                                  decomp.ndo, decomp.multiproc, decomp.gauge_origin)

        # write rdm1s
        if decomp.write != '':
            write_rdm1(mol, decomp.part, mo_coeff, mo_occ, decomp.write, weights)

        return decomp.res

