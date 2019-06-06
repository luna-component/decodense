#!/usr/bin/env python
#
# Author: Janus Juul Eriksen <januseriksen@gmail.com>
#

import sys
import numpy as np
from pyscf import gto, scf, dft, lo, symm


def e_elec(h_core, vj, vk, rdm1):
    """
    this function returns a contribution to a mean-field energy from rdm1:
    E(rdm1) = 2. * Tr[h * rdm1] + Tr[v_eff(rdm1_tot) * rdm1]

    :param h_core: core hamiltonian. numpy array of shape (n_orb, n_orb)
    :param vj: coulumb potential. numpy array of shape (n_orb, n_orb)
    :param vk: exchange potential. numpy array of shape (n_orb, n_orb)
    :param rdm1: orbital specific rdm1. numpy array of shape (n_orb, n_orb)
    :return: scalar
    """
    # contribution from core hamiltonian
    e_core = np.einsum('ij,ji', h_core, rdm1) * 2.

    # contribution from effective potential
    e_veff = np.einsum('ij,ji', vj - vk * .5, rdm1)

    return e_core + e_veff


def e_tot(mol, mf, mo_coeff, dft=False):
    """
    this function returns a sorted orbital-decomposed mean-field energy for a given orbital variant

    :param mol: pyscf mol object
    :param mf: pyscf mean-field object
    :param mo_coeff: mo coefficients. numpy array of shape (n_orb, n_orb)
    :param dft: dft logical. bool
    :return: numpy array of shape (n_occ,)
    """
    # compute 1-RDM (in AO representation)
    rdm1 = mf.make_rdm1(mo_coeff, mf.mo_occ)

    # core hamiltonian
    h_core = mol.intor_symmetric('int1e_kin') + mol.intor_symmetric('int1e_nuc')

    # mean-field effective potential
    if dft:

        v_dft = mf.get_veff(mol, rdm1)
        vj, vk = v_dft.vj, v_dft.vk

    else:

        vj, vk = mf.get_jk(mol, rdm1)

    # init orbital energy array
    e_orb = np.zeros(mol.n_occ)

    # loop over orbitals
    for orb in range(mol.n_occ):

        # orbital-specific 1rdm
        rdm1_orb = np.einsum('ip,jp->ij', mo_coeff[:, [orb]], mo_coeff[:, [orb]])

        # energy from individual orbitals
        e_orb[orb] = e_elec(h_core, vj, vk, rdm1_orb)

    return np.sort(e_orb)


def loc_orbs(mol, mf, variant):
    """
    this function returns a set of localized MOs of a specific variant

    :param mol: pyscf mol object
    :param mf: pyscf mf object
    :param variant: localization variant. string
    :return: numpy array of shape (n_orb, n_orb)
    """
    # copy MOs from mean-field object
    mo_coeff = np.copy(mf.mo_coeff)

    # init localizer
    if variant == 'boys':

        # Foster-Boys procedure
        loc = lo.Boys(mol, mo_coeff[:, :mol.n_occ])

    elif variant == 'pm':

        # Pipek-Mezey procedure
        loc = lo.PM(mol, mo_coeff[:, :mol.n_occ])

    elif variant == 'er':

        # Edmiston-Ruedenberg procedure
        loc = lo.ER(mol, mo_coeff[:, :mol.n_occ])

    elif variant == 'ibo':

        # AO overlap matrix
        s = mol.intor_symmetric('int1e_ovlp')

        # compute IAOs
        a = lo.iao.iao(mol, mo_coeff[:, :mol.n_occ])

        # orthogonalize IAOs
        a = lo.vec_lowdin(a, s)

        # IBOs via Pipek-Mezey procedure
        loc = lo.ibo.PM(mol, mo_coeff[:, :mol.n_occ], a)

    else:

        raise RuntimeError('unknown localization procedure')

    # convergence threshold
    loc.conv_tol = 1.0e-10

    # localize occupied orbitals
    mo_coeff[:, :mol.n_occ] = loc.kernel()

    return mo_coeff


def set_ncore(mol):
    """
    this function return number of core orbitals

    :param mol: pyscf mol object
    :return: integer
    """
    # init ncore
    ncore = 0

    # loop over atoms
    for i in range(mol.natm):

        if mol.atom_charge(i) > 2: ncore += 1
        if mol.atom_charge(i) > 12: ncore += 4
        if mol.atom_charge(i) > 20: ncore += 4
        if mol.atom_charge(i) > 30: ncore += 6

    return ncore


def energy_nuc(mol):
    """
    this function returns the nuclear repulsion energy for all atoms of the system

    :param mol: pyscf mol object
    :return: numpy array of shape (n_atom,)
    """
    # charges
    charges = mol.atom_charges()

    # coordinates
    coords = mol.atom_coords()

    # init e_nuc
    e_nuc = np.zeros(mol.n_atom)

    # loop over atoms
    for j in range(mol.n_atom):

        # charge and coordinates of atom_j
        q_j = charges[j]
        r_j = coords[j]

        # loop over atoms < atom_j
        for i in range(j):

            # charge and coordinates of atom_i
            q_i = charges[i]
            r_i = coords[i]

            # distance between atom_j & atom_i
            r = np.linalg.norm(r_i - r_j)

            # repulsion energy
            e_nuc[j] += (q_i * q_j) / r

    return e_nuc


def main():
    """ main program """

    # read in molecule argument
    if len(sys.argv) != 3:
        sys.exit('\n missing or too many arguments: python orb_decomp.py molecule loc_proc\n')

    # set molecule
    molecule = sys.argv[1]
    loc_proc = sys.argv[2]


    # init molecule
    mol = gto.Mole()
    mol.build(
    verbose = 0,
    output = None,
    atom = open('structures/'+molecule+'.xyz').read(),
    basis = '631g',
    symmetry = True,
    )


    # singlet check
    assert mol.spin == 0, 'decomposition scheme only implemented for singlet states'


    # molecular dimensions
    mol.n_atom = len(mol._atm)
    mol.n_core = set_ncore(mol)
    mol.n_occ = mol.nelectron // 2


    # nuclear repulsion energy
    e_nuc = np.sum(energy_nuc(mol))


    # init and run HF calc
    mf_hf = scf.RHF(mol)
    mf_hf.run()
    assert mf_hf.converged, 'HF not converged'

    # init and run DFT (B3LYP) calc
    mf_dft = dft.RKS(mol)
    mf_dft.xc = 'b3lyp'
    mf_dft.run()
    assert mf_hf.converged, 'DFT not converged'


    # value of XC functional on grid
    e_xc = mf_dft._numint.nr_rks(mol, mf_dft.grids, mf_dft.xc, mf_dft.make_rdm1(mf_dft.mo_coeff, mf_dft.mo_occ))[1]


    # decompose HF energy by means of canonical orbitals
    mo_coeff = mf_hf.mo_coeff
    e_hf = e_tot(mol, mf_hf, mo_coeff)

    # decompose HF energy by means of localized MOs
    mo_coeff = loc_orbs(mol, mf_hf, loc_proc)
    e_hf_loc = e_tot(mol, mf_hf, mo_coeff)

    # decompose DFT energy by means of canonical orbitals
    mo_coeff = mf_dft.mo_coeff
    e_dft = e_tot(mol, mf_dft, mo_coeff, dft=True)

    # decompose DFT energy by means of localized MOs
    mo_coeff = loc_orbs(mol, mf_dft, loc_proc)
    e_dft_loc = e_tot(mol, mf_dft, mo_coeff, dft=True)


    # print results
    print('\n\n results for: {:} with localization procedure: {:}\n\n'.format(molecule, loc_proc))
    print('  MO  |       hf      |     hf-loc    |      dft      |     dft-loc')
    print('-------------------------------------------------------------------------')
    for i in range(e_hf.size):
        print('  {:>2d}  | {:>10.3f}    | {:>10.3f}    | {:>10.3f}    | {:>10.3f}'. \
                format(i, e_hf[i], e_hf_loc[i], e_dft[i], e_dft_loc[i]))
    print('-------------------------------------------------------------------------')
    print('-------------------------------------------------------------------------')
    print('  sum | {:>12.5f}  | {:>12.5f}  | {:>12.5f}  | {:>12.5f}'. \
            format(np.sum(e_hf), np.sum(e_hf_loc), np.sum(e_dft), np.sum(e_dft_loc)))
    print('-------------------------------------------------------------------------')
    print('  nuc | {:>+12.5f}  | {:>+12.5f}  | {:>+12.5f}  | {:>+12.5f}'. \
            format(e_nuc, e_nuc, e_nuc, e_nuc))
    print('  xc  |      N/A      |      N/A      | {:>12.5f}  | {:>12.5f}'. \
            format(e_xc, e_xc))
    print('-------------------------------------------------------------------------')
    print('-------------------------------------------------------------------------')
    print('  sum | {:>12.5f}  | {:>12.5f}  | {:>12.5f}  | {:>12.5f}'. \
            format(np.sum(e_hf) + e_nuc, np.sum(e_hf_loc) + e_nuc, \
                   np.sum(e_dft) + e_xc + e_nuc, np.sum(e_dft_loc) + e_xc + e_nuc))
    print('\n *** HF reference energy  = {:.5f}'. \
            format(mf_hf.e_tot))
    print(' *** DFT reference energy = {:.5f}\n\n'. \
            format(mf_dft.e_tot))


if __name__ == '__main__':
    main()


