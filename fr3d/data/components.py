from fr3d.data.base import EntitySelector
from fr3d.data.base import AtomProxy
from fr3d.data.atoms import Atom
from fr3d import definitions as defs
from fr3d.geometry.superpositions import besttransformation
from fr3d.geometry import angleofrotation as angrot
import numpy as np
NHBondLength=1
from fr3d.unit_ids import encode

def unit_vector(v):
    return v / np.linalg.norm(v)

# This function calculates an angle from 0 to 180 degrees between two vectors
def angle_between_vectors(vec1, vec2):
    if len(vec1) == 3 and len(vec2) == 3:
        cosang = np.dot(vec1, vec2)
        sinang = np.linalg.norm(np.cross(vec1, vec2))
        angle = np.arctan2(sinang, cosang)
        return 180*angle/np.pi
    else:
        return None

# This function calculates an angle from 0 to 180 degrees between two vectors
def angle_between_three_points(P1,P2,P3):
    if len(P1) == 3 and len(P2) == 3 and len(P3) == 3:
        return angle_between_vectors(P1-P2,P3-P2)
    else:
        return None

# return positions of hydrogens making a tetrahedron with center C and vertices P1 and P2
def pyramidal_hydrogens(P1,C,P2,bondLength=1):

    # infer positions one way
    V1 = P1
    V2 = P2
    # vector from V2 to C
    u = unit_vector(C-V2)
    # construct Rodrigues rotation matrix
    # matrix to rotate 120 degrees around vector u
    W = np.array([[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]])
    R = np.identity(3) + (np.sqrt(3)/2)*W + 1.5 * np.dot(W,W)
    # remaining vertices are vector from C to V1 rotated 120 degrees in either direction
    V3 = C + bondLength * unit_vector(np.dot(R,V1-C))
    V4 = C + bondLength * unit_vector(np.dot(np.transpose(R),V1-C))

    # infer positions the other way
    V1 = P2
    V2 = P1
    # vector from V2 to C
    u = unit_vector(C-V2)
    # construct Rodrigues rotation matrix
    # matrix to rotate 120 degrees around vector u
    W = np.array([[0,-u[2],u[1]],[u[2],0,-u[0]],[-u[1],u[0],0]])
    R = np.identity(3) + (np.sqrt(3)/2)*W + 1.5 * np.dot(W,W)
    # remaining vertices are vector from C to V1 rotated 120 degrees in either direction
    VV4 = C + bondLength * unit_vector(np.dot(R,V1-C))
    VV3 = C + bondLength * unit_vector(np.dot(np.transpose(R),V1-C))

    # average the two inferred positions
    P3 = (V3+VV3)/2
    P4 = (V4+VV4)/2

    # diagnostics if desired
    if 1 > 10:
        print("pyramidal_hydrogens V3, VV3 distance",np.linalg.norm(V3-VV3))
        print("pyramidal_hydrogens V4, VV4 distance",np.linalg.norm(V4-VV4))
        print("pyramidal_hydrogens P1-C-P2 angle",angle_between_three_points(P1,C,P2),"as input")
        print("pyramidal_hydrogens P1-C-P3 angle",angle_between_three_points(P1,C,P3),"as inferred")
        print("pyramidal_hydrogens P1-C-P4 angle",angle_between_three_points(P1,C,P4),"as inferred")
        print("pyramidal_hydrogens P2-C-P3 angle",angle_between_three_points(P2,C,P3),"as inferred")
        print("pyramidal_hydrogens P2-C-P4 angle",angle_between_three_points(P2,C,P4),"as inferred")
        print("pyramidal_hydrogens P3-C-P4 angle",angle_between_three_points(P3,C,P4),"as inferred")
    return P3, P4

def planar_hydrogens(P1,P2,P3,bondLength=1):

    A = unit_vector(P2 - P1)
    N1 = P3 + A*bondLength
    B = unit_vector(P3 - P2)
    N2 = P3 + (B - A)*bondLength

    # diagnostics if desired
    if 1 > 10:
        print("planar_hydrogens P1-P2-P3 angle",angle_between_three_points(P1,P2,P3),"as input")
        print("planar_hydrogens P2-P3-N1 angle",angle_between_three_points(P2,P3,N1),"as inferred")
        print("planar_hydrogens P2-P3-N2 angle",angle_between_three_points(P2,P3,N2),"as inferred")
    return N1, N2

class Component(EntitySelector):
    """This represents things like nucleic acids, amino acids, small molecules
    and ligands.
    """

    def __init__(self, atoms, pdb=None, model=None, type=None, chain=None,
                 symmetry=None, sequence=None, number=None, index=None,
                 insertion_code=None, polymeric=None, alt_id=None, inferhydrogens=True):
        """Create a new Component.

        :atoms: The atoms this component is composed of.
        :pdb: The pdb this is a part of.
        :model: The model number.
        """

        self._atoms = atoms
        self.pdb = pdb
        self.model = model
        self.type = type
        self.chain = chain
        self.symmetry = symmetry
        self.sequence = sequence
        self.number = number
        self.index = index
        self.insertion_code = insertion_code
        self.polymeric = polymeric
        self.alt_id = alt_id
        self.base_center = None
        self.rotation_matrix = None

        # for bases, calculate and store rotation_matrix
        # calculate and store base_center; especially for modified nt without all heavy atoms
        self.calculate_rotation_matrix()

        # initialize centers so they can be used to infer hydrogens
        self.centers = AtomProxy(self._atoms)

        # add hydrogen atoms to standard bases and amino acids
        if inferhydrogens:
            self.infer_hydrogens()

        # initialize centers again to include hydrogens
        self.centers = AtomProxy(self._atoms)

        if self.base_center is not None:
            self.centers.__setitem__('base',self.base_center)

        if self.sequence in defs.nt_sugar:
            atoms = defs.nt_sugar[self.sequence]
            self.centers.define('nt_sugar', atoms)

        if self.sequence in defs.nt_phosphate:
            atoms = defs.nt_phosphate[self.sequence]
            self.centers.define('nt_phosphate', atoms)

        # attempt to add sugar and phosphate centers for all modified nucleotides
        if self.sequence in defs.modified_nucleotides:
            atoms = defs.nt_sugar['A']
            self.centers.define('nt_sugar', atoms)
            atoms = defs.nt_phosphate['A']
            self.centers.define('nt_phosphate', atoms)

        if self.sequence in defs.aa_fg:
            atoms = defs.aa_fg[self.sequence]
            self.centers.define('aa_fg', atoms)

        if self.sequence in defs.aa_backbone:
            atoms = defs.aa_backbone[self.sequence]
            self.centers.define('aa_backbone', atoms)

    def atoms(self, **kwargs):
        """Get, filter and sort the atoms in this component. Access is as
        described by EntitySelector.

        :kwargs: The keyword arguments to filter and sort by.
        :returns: A list of the requested atoms.
        """

        name = kwargs.get('name')
        if isinstance(name, basestring):
            definition = self.centers.definition(name)
            if definition:
                kwargs['name'] = definition

        return EntitySelector(self._atoms, **kwargs)

    def coordinates(self, **kwargs):
        """Get the coordaintes of all atoms in this component. This will
        filter to the requested atoms, sort and then provide a numpy array
        of all coordinates for the given atoms.

        :kwargs: Arguments to filter and sort by.
        :returns: A numpy array of the coordinates.
        """
        return np.array([atom.coordinates() for atom in self.atoms(**kwargs)])

    def select(self, **kwargs):
        """Select a group of atoms to create a new component out of.

        :kwargs: As for atoms.
        :returns: A new Component
        """
        return Component(list(self.atoms(**kwargs)),
                         pdb=self.pdb,
                         model=self.model,
                         type=self.type,
                         chain=self.chain,
                         symmetry=self.symmetry,
                         sequence=self.sequence,
                         number=self.number,
                         index=self.index,
                         insertion_code=self.insertion_code,
                         alt_id=self.alt_id,
                         polymeric=self.polymeric,
                         inferhydrogens=False)

    def is_complete(self, names, key='name'):
        """This checks if we can find all atoms in this entity with the given
        names. This assumes that the names for each atom are unique. If you
        wish to use something other than name use the key argument. However, it
        must provide a unique value for each atom, if several atoms with the
        same value are found will cause the function to behave oddly.

        :names: The list of names to check for.
        :key: The key to use for getting atoms. Defaults to name.
        :returns: True if all atoms with the given name are present.
        """
        kwargs = {key: names}
        found = list(self.atoms(**kwargs))
        return len(found) == len(names)

    def calculate_rotation_matrix(self):
        """Calculate a rotation matrix that will rotate the atoms in an RNA
        base into a standard orientation in the xy plane with the Watson-
        Crick edge in the positive x and y quadrant.
        """

        if self.sequence not in defs.NAbaseheavyatoms and \
                self.sequence not in defs.modified_nucleotides:
            return None

        R = []   # 3d coordinates of observed base
        S = []   # 3d coordinates of standard base in xy plane

        if self.sequence in defs.NAbaseheavyatoms:
            baseheavy = defs.NAbaseheavyatoms[self.sequence]
            for atom in self.atoms(name=baseheavy):
                R.append(atom.coordinates())
                S.append(defs.NAbasecoordinates[self.sequence][atom.name])

        if self.sequence in defs.modified_nucleotides:
            current = defs.modified_nucleotides[self.sequence]
            standard_coords = defs.NAbasecoordinates[current["standard"]]
            for atom in self.atoms(name=current["atoms"].keys()):
                R.append(list(atom.coordinates()))
                S.append(standard_coords[atom.name])

        R = np.array(R)
        R = R.astype(np.float)
        S = np.array(S)

        try:
            rotation_matrix, fitted, meanR, rmsd, sse, meanS = \
                besttransformation(R, S)
        except:
            if len(R) != len(S):
                print("%s Rotation matrix calculation failed, sizes %d and %d" % (self.unit_id(),len(R),len(S)))
            elif len(R) < 3:
                print("%s Rotation matrix calculation failed, %d new atoms" % (self.unit_id(),len(R)))
            elif len(S) < 3:
                print("%s Rotation matrix calculation failed, %d standard atoms" % (self.unit_id(),len(S)))
            else:
                print("%s Rotation matrix calculation failed, not sure why" % self.unit_id())

            return None

        self.rotation_matrix = rotation_matrix

        # map the origin out to where the center of the base should be
        if self.sequence in defs.NAbaseheavyatoms:
            # standard bases are designed to have meanS zero; less work
            self.base_center = meanR
        else:
            # some modified bases are missing some heavy atoms, meanS not zero
            self.base_center = np.subtract(meanR,np.dot(rotation_matrix,meanS))


    def infer_hydrogens(self):
        """Infer the coordinates of the hydrogen atoms of this component.
        RNA and DNA work, and amino acids are being added.
        This code only adds hydrogens with their name, but the Atom entity
        does not have the full unit ID of the atom, unlike the heavy atoms
        taken from the CIF file.
        """

        try:

            if self.sequence in defs.NAbasehydrogens:
                hydrogens = defs.NAbasehydrogens[self.sequence]
                coordinates = defs.NAbasecoordinates[self.sequence]

                current_hydrogens = [a.name for a in self._atoms if "H" in a.name]
                #print("Current hydrogens: ",current_hydrogens)

                for hydrogenatom in hydrogens:
                    if not hydrogenatom in current_hydrogens:
                        #print("Adding",hydrogenatom,"to",self.unit_id())
                        hydrogencoordinates = coordinates[hydrogenatom]
                        newcoordinates = self.base_center + \
                            np.dot(self.rotation_matrix, hydrogencoordinates)
                        self._atoms.append(Atom(name=hydrogenatom,
                                                x=newcoordinates[0, 0],
                                                y=newcoordinates[0, 1],
                                                z=newcoordinates[0, 2]))

            elif self.sequence == "ARG":

                N1,N2 = planar_hydrogens(self.centers["NE"],self.centers["CZ"],self.centers["NH1"],NHBondLength)
                self._atoms.append(Atom(name="HH11",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HH12",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = planar_hydrogens(self.centers["NE"],self.centers["CZ"],self.centers["NH2"])
                self._atoms.append(Atom(name="HH22",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HH21",x=N2[0],y=N2[1],z=N2[2]))

                # the following lines assume that NH2 is closer to CD
                # than NH1 is however, some structures aren't labeled
                # that way, and so either N1 or N2 could be the correct
                # location for HE
                N1,N2 = planar_hydrogens(self.centers["NH1"],self.centers["CZ"],self.centers["NE"])
                self._atoms.append(Atom(name="HE",x=N1[0],y=N1[1],z=N1[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CG"],self.centers["CD"],self.centers["NE"])
                self._atoms.append(Atom(name="HD3",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HD2",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CB"],self.centers["CG"],self.centers["CD"])
                self._atoms.append(Atom(name="HG2",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HG3",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CA"],self.centers["CB"],self.centers["CG"])
                self._atoms.append(Atom(name="HB2",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HB3",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["C"],self.centers["CA"],self.centers["CB"])
                self._atoms.append(Atom(name="HA",x=N2[0],y=N2[1],z=N2[2]))

            elif self.sequence == "LYS":

                N1,N2 = planar_hydrogens(self.centers["CD"],self.centers["CE"],self.centers["NZ"],NHBondLength)
                self._atoms.append(Atom(name="HZ3",x=N1[0],y=N1[1],z=N1[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CG"],self.centers["CD"],self.centers["CE"])
                self._atoms.append(Atom(name="HD2",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HD3",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CB"],self.centers["CG"],self.centers["CD"])
                self._atoms.append(Atom(name="HG2",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HG3",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CD"],self.centers["CE"],self.centers["NZ"])
                self._atoms.append(Atom(name="HE2",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HE3",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["CA"],self.centers["CB"],self.centers["CG"])
                self._atoms.append(Atom(name="HB2",x=N1[0],y=N1[1],z=N1[2]))
                self._atoms.append(Atom(name="HB3",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = pyramidal_hydrogens(self.centers["C"],self.centers["CA"],self.centers["CB"])
                self._atoms.append(Atom(name="HA",x=N2[0],y=N2[1],z=N2[2]))

                N1,N2 = planar_hydrogens(self.centers["CD"],self.centers["HD3"],self.centers["NZ"])
                self._atoms.append(Atom(name="HZ2",x=N1[0],y=N1[1],z=N1[2]))

        except:
            print self.unit_id(), "Adding hydrogens failed"


    def transform(self, transform_matrix):
        """Create a new component from "self" by applying the 4x4 transformation
        matrix. This does not keep the rotation matrix if any,
        but will keep any added hydrogens.

        :transform_matrix: The 4x4 transformation matrix to apply.
        :returns: A new Component with the same properties except with
        transformed coordinates.
        """

        atoms = [atom.transform(transform_matrix) for atom in self.atoms()]
        comp = Component(atoms, pdb=self.pdb,
                         model=self.model,
                         type=self.type,
                         chain=self.chain,
                         symmetry=self.symmetry,
                         sequence=self.sequence,
                         number=self.number,
                         index=self.index,
                         insertion_code=self.insertion_code,
                         alt_id=self.alt_id,
                         polymeric=self.polymeric,
                         inferhydrogens=False)
        return comp

    def translate_rotate(self, residue):
        reference = self.centers["base"]
        rotation = self.rotation_matrix
        for atom in residue.atoms():
            atom_coord = atom.coordinates()
            dist_translate = np.subtract(atom_coord, reference)
            dist_aa_matrix = np.matrix(dist_translate)
            rotated_atom = dist_aa_matrix * rotation
            coord_array = np.array(rotated_atom)
            a = coord_array.flatten()
            transformed_coord = a.tolist()
        return transformed_coord

    def translate_rotate_component(self, component):
        """Translate and rotate the atoms in component according to
        the translation and rotation that will bring self to standard
        position at the origin.
        :param Component residue:  the residue to move
        :returns Component newcomp
        """

        atoms = [self.translate_rotate_atom(atom) for atom in component.atoms()]
        newcomp = Component(atoms, pdb=component.pdb,
                         model=component.model,
                         type=component.type,
                         chain=component.chain,
                         symmetry=component.symmetry,
                         sequence=component.sequence,
                         number=component.number,
                         index=component.index,
                         insertion_code=component.insertion_code,
                         alt_id=component.alt_id,
                         polymeric=component.polymeric,
                         inferhydrogens=False)
        return newcomp

    def translate_rotate_atom(self, atom):
        """Translate and rotate atom according to
        the translation and rotation that will bring self to standard
        position at the origin.

        :param Atom atom: The Atom to move.
        :returns Atom: The moved atom.
        """

        atom_coord = atom.coordinates()
        translated_coord = np.subtract(atom_coord, self.base_center)
        translated_coord_matrix = np.matrix(translated_coord)
        rotated_coord = translated_coord_matrix * self.rotation_matrix
        coord_array = np.array(rotated_coord)
        a = coord_array.flatten()
        x, y, z = a.tolist()
        return Atom(x=x, y=y, z=z,
                    pdb=atom.pdb,
                    model=atom.model,
                    chain=atom.chain,
                    component_id=atom.component_id,
                    component_number=atom.component_number,
                    component_index=atom.component_index,
                    insertion_code=atom.insertion_code,
                    alt_id=atom.alt_id,
                    group=atom.group,
                    type=atom.type,
                    name=atom.name,
                    symmetry=atom.symmetry,
                    polymeric=atom.polymeric)

    def standard_transformation(self):
        """Returns a 4X4 transformation matrix which can be used to transform
        any component to the same relative location as the "self" argument in
        its standard location. If this is not an RNA component then this returns
        None.
        :returns: A numpy array suitable for input to self.transform to produce
        a transformed component.
        """

        if 'base' not in self.centers:
            return None
        base_center = self.centers["base"]
        if len(base_center) == 0:
            return None
        seq = self.sequence
        dist_translate = base_center

        rotation_matrix_transpose = self.rotation_matrix.transpose()

        matrix = np.zeros((4, 4))
        matrix[0:3, 0:3] = rotation_matrix_transpose
        matrix[0:3, 3] = -np.dot(rotation_matrix_transpose, dist_translate)
        matrix[3, 3] = 1.0

        return matrix

    def translate(self, aa_residue):
        if 'base' not in self.centers:
            return None
        rotation = self.rotation_matrix
        for atom in aa_residue:
            dist_translate = np.subtract(atom, self.centers["base"])
            rotated_atom = dist_translate*rotation
            coord_array = np.array(rotated_atom)
            a = coord_array.flatten()
            coord = a.tolist()
        return coord


    def unit_id(self):
        """Compute the unit id of this Component.

        :returns: The unit id.
        """

        return encode({
            'pdb': self.pdb,
            'model': self.model,
            'chain': self.chain,
            'component_id': self.sequence,
            'component_number': self.number,
            'alt_id': self.alt_id,
            'insertion_code': self.insertion_code,
            'symmetry': self.symmetry
        })

    def atoms_within(self, other, cutoff, using=None, to=None, min_number=1):
        """Determine if there are any atoms from another component within some
        distance.

        :other: Another component to compare agains.
        :using: The atoms from this component to compare with.
        :to: The atoms from the other component to compare against.
        :cutoff: The distances atoms must be within. Default 4.0
        """

        kw1 = {}
        if using:
            kw1['name'] = using

        kw2 = {}
        if to:
            kw2['name'] = to

        n = 0
        for atom1 in self.atoms(**kw1):
            for atom2 in other.atoms(**kw2):
                if atom1.distance(atom2) <= abs(cutoff):
                    n = n+1

        if n >= min_number:
            return True

    def distance(self, other, using='*', to='*'):
        """Compute a center center distance between this and another component.

        :other: The other component to get distance to.
        :using: A list of atom names to use for this component. Defaults to '*'
        meaning all atoms.
        :to: A list of atoms names for the second component. Defaults to '*'
        meaning all atoms.
        :returns: The distance between the two centers.
        """
        coordinates = self.centers[using]
        other_coord = other.centers[to]
        distance = np.subtract(coordinates, other_coord)
        return np.linalg.norm(distance)

    def __len__(self):
        """Compute the length of this Component. This is the number of atoms in
        this residue.

        :returns: The number of atoms.
        """
        return len(self._atoms)

    def __eq__(self, other):
        return isinstance(other, Component) and \
            self.pdb == other.pdb and \
            self.model == other.model and \
            self.chain == other.chain and \
            self.symmetry == other.symmetry and \
            self.sequence == other.sequence and \
            self.number == other.number and \
            self.insertion_code == other.insertion_code and \
            self.alt_id == other.alt_id

    def __repr__(self):
        return '<Component %s>' % self.unit_id()

    def angle_between_normals(self, aa_residue):
        vec1 = self.normal_calculation()
        vec2 = aa_residue.normal_calculation()
        return angrot.angle_between_planes(vec1, vec2)

    def normal_calculation(self):
        key = self.sequence
        P1 = self.centers[defs.planar_atoms[key][0]]
        P2 = self.centers[defs.planar_atoms[key][1]]
        P3 = self.centers[defs.planar_atoms[key][2]]
        vector = np.cross((P2 - P1), (P3-P1))
        return vector

    def enough_hydrogen_bonds(self, second, min_distance=4, min_bonds=2):
        """Calculates atom to atom distance of part "aa_part" of neighboring
        amino acids of type "aa" from each atom of base. Only returns a pair
        of aa/nt if two or more atoms are within the cutoff distance.
        """

        HB_atoms = set(['N', 'NH1','NH2','NE','NZ','ND1','NE2','O','OD1','OE1','OE2', 'OG', 'OH'])
        n = 0
        base_seq = self.sequence()
        for base_atom in self.atoms(name=defs.NAbaseheavyatoms[base_seq]):
            for aa_atom in second.atoms(name=defs.aa_fg[second.sequence]):
                distance = np.subtract(base_atom.coordinates(), aa_atom.coordinates())
                distance = np.linalg.norm(distance)
                if distance <= min_distance and aa_atom.name in HB_atoms:
                    n = n + 1
                    if n > min_bonds:
                        return True
        return False

    def stacking_tilt(aa_residue, aa_coordinates):
        baa_dist_list = []

        for aa_atom in aa_residue.atoms(name=defs.aa_fg[aa_residue.sequence]):
            key = aa_atom.name
            aa_z = aa_coordinates[key][2]
            baa_dist_list.append(aa_z)
        max_baa = max(baa_dist_list)
        min_baa = min(baa_dist_list)
        diff = max_baa - min_baa
        #print aa_residue.unit_id(), diff
        if diff <= defs.tilt_cutoff[aa_residue.sequence]:
            return "stacked"
