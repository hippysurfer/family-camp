import datetime
import sys
import logging
from collections import Counter

from pyevolve import GSimpleGA
from pyevolve.G1DList import G1DList
from pyevolve.Initializators import G1DBinaryStringInitializator

t = datetime.time

log = logging.getLogger(__name__)


class Activity:

    ALL = {}

    def __init__(self, name, id, slots):
        self.name = name
        self.id = id
        self.slots = slots

        self.__class__.ALL[id] = self

    @classmethod
    def from_id(cls, id):
        return cls.ALL[id]


class Member:

    def __init__(self, name, activities):
        self.name = name
        self.activities = activities


class Family:

    ALL = {}

    def __init__(self, name, id, members):
        self.name = name
        self.id = id
        self.members = members

        self.__class__.ALL[id] = self

    def get_members(self):
        return self.members

    @classmethod
    def from_id(cls, id):
        return cls.ALL[id]

    @classmethod
    def get_all(cls):
        return cls.ALL.values()


act1 = Activity(name="Activity1",
                id=0b000,
                slots={0b000: (t(9, 0), t(10, 0)),
                       0b001: (t(10, 15), t(11, 15))})

act2 = Activity(name="Activity2",
                id=0b001,
                slots={0b000: (t(9, 0), t(9, 25)),
                       0b001: (t(10, 0), t(10, 25))})

f1member1 = Member("Joe Blogs", [act1])
f1member2 = Member("Jane Blogs", [act1, act2])
f1 = Family("The Blogs", 0, [f1member1, f1member2])

f2member1 = Member("Fred Blue", [act2])
f2member2 = Member("Chloe Blue", [act2])
f2 = Family("The Blues", 1, [f2member1, f2member1])

f1member1 = Member("Joe Greans", [act1])
f1member2 = Member("Jane Greans", [act1, act2])
f3 = Family("The Greans", 2, [f1member1, f1member2])

f2member1 = Member("Fred Browns", [act2])
f2member2 = Member("Chloe Browns", [act2])
f4 = Family("The Browns", 3, [f2member1, f2member1])


def list_to_int(l):
    return int("".join(str(i) for i in l), 2)


class Schedule(list):

    def __str__(self):
        out = []
        for activity, slot, family1, family2 in self:
            out.append("{} {} {} {}".format(
                activity.name, slot, family1.name, family2.name
            ))
        return "\n".join(out)


class Chromosome:

    def __init__(self, schedule):
        self.schedule = Schedule(schedule)

    def __str__(self):
        return str(self.schedule)

    def get_score(self):
        score = 0.0

        #import pdb
        #pdb.set_trace()

        for family in Family.get_all():
            for member in family.get_members():
                for (activity, slot, family1, family2) in self.schedule:
                    for fam in (family1, family2):
                        if family.id == fam.id:
                            if activity in member.activities:
                                score += 1

        family_pair_map = {}
        for (activity, slot, family1, family2) in self.schedule:
            if (family1, family2) in family_pair_map:
                score -= 0.5
            else:
                family_pair_map[(family1, family2)] = 1


        # A Family should not appear in a activity twice
        act_family_map = {}
        for activity, slot, family1, family2 in self.schedule:
            for fam in (family1, family2):
                if (activity.id in act_family_map and
                    fam in act_family_map[activity.id]):
                    score = 0
                    log.debug("Duplicate families")
                    break
                else:
                    act_family_map[activity.id] = {fam: 1}

        # Check if any activities / slots are listed more than once.
        c = Counter([(activity.id, slot) for activity, slot, family1, family2
                     in self.schedule])

        if len([v for v in c.values() if v > 1]) > 0:
            log.debug("duplicate activity / slots {}".format(c))
            score = 0

        return score

    @classmethod
    def from_list(cls, l):
        schedule = []
        i = 0
        while i < len(l):
            schedule.append(
                (Activity.from_id(list_to_int(l[i:i+1])),
                 list_to_int(l[i+1:i+2]),
                 Family.from_id(list_to_int(l[i+2:i+4])),
                 Family.from_id(list_to_int(l[i+4:i+6]))))
            i += 6

        return cls(schedule)



# class Genome(GenomeBase):

#     def __init__(self, length=4):
#         GenomeBase.__init__(self)
#         self.genomeString = []
#         self.stringLength = length
#         self.initializator.set(Consts.CDefG1DBinaryStringInit)
#         self.mutator.set(Consts.CDefG1DBinaryStringMutator)
#         self.crossover.set(Consts.CDefG1DBinaryStringCrossover)

#     def getListSize(self):
#         return self.stringLength

#     def copy(self, g):
#         """ Copy genome to 'g' """
#         GenomeBase.copy(self, g)
#         g.stringLength = self.stringLength
#         g.genomeString = self.genomeString[:]

#     def clone(self):
#         """ Return a new instace copy of the genome """
#         newcopy = Genome(self.stringLength)
#         self.copy(newcopy)
#         return newcopy


def eval_func(chromosome):
    c = Chromosome.from_list(chromosome.genomeList)

    return c.get_score()


if __name__ == '__main__':
    #log.addHandler(logging.StreamHandler(stream=sys.stderr))
    log.setLevel(logging.DEBUG)
    log.debug("Debug is on")

    genome = G1DList(6 * 4)
    genome.initializator.set(G1DBinaryStringInitializator)
    genome.evaluator.set(eval_func)
    ga = GSimpleGA.GSimpleGA(genome)
    ga.evolve(freq_stats=10)
    print Chromosome.from_list(ga.bestIndividual())
