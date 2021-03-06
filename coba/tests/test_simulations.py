import unittest

import timeit

from abc import ABC, abstractmethod
from typing import List, Sequence, Tuple, cast

from coba.execution import ExecutionContext, NoneCache, NoneLogger
from coba.preprocessing import (
    PartMeta, FullMeta, InferredEncoder,  NumericEncoder, 
    OneHotEncoder, StringEncoder, FactorEncoder
)
from coba.simulations import (
    JsonSimulation, Reward, Key, Choice, Interaction, Simulation,
    ClassificationSimulation, MemorySimulation, LambdaSimulation
)

ExecutionContext.Logger = NoneLogger()

def _choices(interaction: Interaction) -> Sequence[Tuple[Key,Choice]]:
    return [  (interaction.key, a) for a in range(len(interaction.actions))]

class Simulation_Interface_Tests(ABC):

    @abstractmethod
    def _make_simulation(self) -> Tuple[Simulation, Sequence[Interaction], Sequence[Sequence[Reward]]]:
        ...

    def test_interactions_is_correct(self) -> None:

        simulation, expected_interactions, expected_rewards = self._make_simulation()

        actual_interactions = simulation.interactions
        actual_rewards      = [simulation.rewards(_choices(i)) for i in actual_interactions ]

        cast(unittest.TestCase, self).assertEqual(len(actual_interactions), len(expected_interactions))

        for actual_inter, expected_inter, in zip(actual_interactions, expected_interactions):
            cast(unittest.TestCase, self).assertEqual(actual_inter.context, expected_inter.context)
            cast(unittest.TestCase, self).assertCountEqual(actual_inter.actions, expected_inter.actions)

        for actual_reward, expected_reward in zip(actual_rewards, expected_rewards):
            cast(unittest.TestCase, self).assertCountEqual(actual_reward, expected_reward)

    def test_interactions_is_reiterable(self) -> None:

        simulation = self._make_simulation()[0]

        for interaction1,interaction2 in zip(simulation.interactions, simulation.interactions):

            interaction1_rewards = simulation.rewards(_choices(interaction1))
            interaction2_rewards = simulation.rewards(_choices(interaction2))

            cast(unittest.TestCase, self).assertEqual(interaction1.context, interaction2.context)
            cast(unittest.TestCase, self).assertSequenceEqual(interaction1.actions, interaction2.actions)
            cast(unittest.TestCase, self).assertSequenceEqual(interaction1_rewards, interaction2_rewards)

class JsonSimulation_Tests(unittest.TestCase):
    def test_simple_init(self):
        json_val = ''' {
            "type": "classification",
            "from": {
                "format"          : "table",
                "table"           : [["a","b","c"], ["s1","2","3"], ["s2","5","6"]],
                "has_header"      : true,
                "column_default"  : { "ignore":false, "label":false, "encoding":"onehot" },
                "column_overrides": { "b": { "label":true, "encoding":"string" } }
            }
        } '''

        with JsonSimulation(json_val) as simulation:
            self.assertEqual(len(simulation.interactions), 2)

class ClassificationSimulation_Tests(Simulation_Interface_Tests, unittest.TestCase):

    def _make_simulation(self) -> Tuple[Simulation, Sequence[Interaction], Sequence[Sequence[Reward]]]:
        
        expected_interactions = [Interaction(1, [(1,0),(0,1)]), Interaction(2, [(1,0),(0,1)])]
        expected_rewards = [[0,1], [1,0]]

        return ClassificationSimulation([1,2], [2,1]), expected_interactions, expected_rewards

    def assert_simulation_for_data(self, simulation, features, labels) -> None:

        self.assertEqual(len(simulation.interactions), len(features))

        labels = OneHotEncoder(simulation._action_set).encode(labels)

        #first we make sure that all the labels are included 
        #in the first interactions actions without any concern for order
        self.assertCountEqual(simulation.interactions[0].actions, set(labels))

        #then we set our expected actions to the first interaction
        #to make sure that every interaction has the exact same actions
        #with the exact same order
        expected_actions = simulation.interactions[0].actions

        for f,l,i in zip(features, labels, simulation.interactions):

            expected_context = f
            expected_rewards = [ int(a == l) for a in i.actions]

            actual_context = i.context
            actual_actions = i.actions
            
            actual_rewards  = simulation.rewards(_choices(i))

            self.assertEqual(actual_context, expected_context)            
            self.assertSequenceEqual(actual_actions, expected_actions)
            self.assertSequenceEqual(actual_rewards, expected_rewards)

    def test_constructor_with_good_features_and_labels1(self) -> None:
        features   = [1,2,3,4]
        labels     = [1,1,0,0]
        simulation = ClassificationSimulation(features, labels)

        self.assert_simulation_for_data(simulation, features, labels)
    
    def test_constructor_with_good_features_and_labels2(self) -> None:
        features   = ["a","b"]
        labels     = ["good","bad"]
        simulation = ClassificationSimulation(features, labels)

        self.assert_simulation_for_data(simulation, features, labels)

    def test_constructor_with_good_features_and_labels3(self) -> None:
        features   = [(1,2),(3,4)]
        labels     = ["good","bad"]
        simulation = ClassificationSimulation(features, labels)

        self.assert_simulation_for_data(simulation, features, labels)

    def test_constructor_with_too_few_features(self) -> None:
        with self.assertRaises(AssertionError): 
            ClassificationSimulation([1], [1,1])

    def test_constructor_with_too_few_labels(self) -> None:
        with self.assertRaises(AssertionError): 
            ClassificationSimulation([1,1], [1])

    def test_from_table_inferred_numeric(self) -> None:
        label_column = 'b'
        default_meta = FullMeta(False,False,InferredEncoder())
        table        = [['a','b','c'],
                        ['1','2','3'],
                        ['4','5','6']]

        simulation = ClassificationSimulation.from_table(table, label_column, default_meta=default_meta)

        self.assert_simulation_for_data(simulation, [(1,3),(4,6)],[2,5])

    def test_from_table_inferred_onehot(self) -> None:
        label_column = 'b'
        default_meta = FullMeta(False,False,InferredEncoder())
        table        = [['a' ,'b','c'],
                        ['s1','2','3'],
                        ['s2','5','6']]

        simulation = ClassificationSimulation.from_table(table, label_column, default_meta=default_meta)

        self.assert_simulation_for_data(simulation, [(1,0,3),(0,1,6)], [2,5])

    def test_from_table_explicit_onehot(self) -> None:
        default_meta = FullMeta(False, False, OneHotEncoder())
        defined_meta = {'b': PartMeta(None, True, StringEncoder()) }
        table        = [['a' ,'b','c'],
                        ['s1','2','3'],
                        ['s2','5','6']]

        simulation = ClassificationSimulation.from_table(table, default_meta=default_meta, defined_meta=defined_meta)

        self.assert_simulation_for_data(simulation, [(1,0,1,0),(0,1,0,1)], ['2','5'])

    def test_simple_from_openml(self) -> None:
        #this test requires interet acess to download the data

        ExecutionContext.FileCache = NoneCache()

        simulation = ClassificationSimulation.from_openml(1116)
        #simulation = ClassificationSimulation.from_openml(273)

        self.assertEqual(len(simulation.interactions), 6598)

        for rnd in simulation.interactions:

            hash(rnd.context)      #make sure these are hashable
            hash(rnd.actions[0]) #make sure these are hashable
            hash(rnd.actions[1]) #make sure these are hashable

            self.assertEqual(len(cast(Tuple,rnd.context)), 167)
            self.assertIn((1,0), rnd.actions)
            self.assertIn((0,1), rnd.actions)
            self.assertEqual(len(rnd.actions),2)
            
            actual_rewards  = simulation.rewards(_choices(rnd))

            self.assertIn(1, actual_rewards)
            self.assertIn(0, actual_rewards)

    @unittest.skip("much of what makes this openml set slow is now tested locally in `test_large_from_table`")
    def test_large_from_openml(self) -> None:
        #this test requires interet acess to download the data

        ExecutionContext.FileCache = NoneCache()

        time = min(timeit.repeat(lambda:ClassificationSimulation.from_openml(154), repeat=1, number=1))

        #print(time)

        #was approximately 18 at best performance
        self.assertLess(time, 30)

    def test_large_from_table(self) -> None:

        table        = [["1","0"]*15]*100000
        label_col    = 0
        default_meta = FullMeta(False,False, FactorEncoder(['1','0']))
        defined_meta = { 2:PartMeta(None,None,NumericEncoder()), 5:PartMeta(None,None,NumericEncoder()) }

        from_table = lambda:ClassificationSimulation.from_table(table, label_col, False, default_meta, defined_meta)

        time = min(timeit.repeat(from_table, repeat=2, number=1))

        #print(time)

        #was approximately 0.6 at best performance
        self.assertLess(time, 3)

    def test_simple_from_csv(self) -> None:
        #this test requires interet acess to download the data

        ExecutionContext.FileCache = NoneCache()

        location     = "http://www.openml.org/data/v1/get_csv/53999"
        default_meta = FullMeta(False, False, NumericEncoder())
        defined_meta = {
            "class"            : PartMeta(None, True, FactorEncoder()), 
            "molecule_name"    : PartMeta(None, None, OneHotEncoder()),
            "ID"               : PartMeta(True, None, None),
            "conformation_name": PartMeta(True, None, None)
        }
        md5_checksum = "4fbb00ba35dd05a29be1f52b7e0faeb6"

        simulation = ClassificationSimulation.from_csv(location, md5_checksum=md5_checksum, default_meta=default_meta, defined_meta=defined_meta)

        self.assertEqual(len(simulation.interactions), 6598)

        for rnd in simulation.interactions:
            hash(rnd.context)      #make sure these are hashable
            hash(rnd.actions[0]) #make sure these are hashable
            hash(rnd.actions[1]) #make sure these are hashable

            self.assertEqual(len(cast(Tuple,rnd.context)), 268)
            self.assertIn((1,0), rnd.actions)
            self.assertIn((0,1), rnd.actions)
            self.assertEqual(len(rnd.actions),2)
            
            actual_rewards = simulation.rewards(_choices(rnd))

            self.assertIn(1, actual_rewards)
            self.assertIn(0, actual_rewards)

    def test_from_json_table(self) -> None:
        
        json_val = '''{
            "format"          : "table",
            "table"           : [["a","b","c"], ["s1","2","3"], ["s2","5","6"]],
            "has_header"      : true,
            "column_default"  : { "ignore":false, "label":false, "encoding":"factor" },
            "column_overrides": { "b": { "label":true, "encoding":"string" } }
        }'''

        simulation = ClassificationSimulation.from_json(json_val)

        self.assert_simulation_for_data(simulation, [(1,1),(2,2)], ['2','5'])

class MemorySimulation_Tests(Simulation_Interface_Tests, unittest.TestCase):

    def _make_simulation(self) -> Tuple[Simulation, Sequence[Interaction], Sequence[Sequence[Reward]]]:
        
        contexts    =  [1,2]
        action_sets = [[1,2,3], [4,5,6]]
        reward_sets = [[0,1,2], [2,3,4]]

        simulation = MemorySimulation(contexts, action_sets, reward_sets)

        expected_interactions = list(map(Interaction[int,int],contexts,action_sets))
        expected_rewards      = reward_sets

        return simulation, expected_interactions, expected_rewards

class LambdaSimulation_Tests(Simulation_Interface_Tests, unittest.TestCase):

    def _make_simulation(self) -> Tuple[Simulation, Sequence[Interaction], Sequence[Sequence[Reward]]]:
        
        contexts    =  [0,1]
        action_sets = [[1,2,3], [4,5,6]]
        reward_sets = [[1,2,3], [3,4,5]]

        def S(i:int) -> int: return contexts[i]
        def A(s:int) -> List[int]: return action_sets[s]
        def R(s:int,a:int) -> int: return a-s

        simulation = LambdaSimulation(2,S,A,R)

        expected_interactions = list(map(Interaction[int,int],contexts,action_sets))
        expected_rewards      = reward_sets
        

        return simulation, expected_interactions, expected_rewards

    def test_correct_number_of_interactions_created(self):
        def C(t:int) -> int:
            return [1,2][t]

        def A(t:int) -> List[int]:
            return [[1,2,3],[4,5,6]][t]
        
        def R(c:int,a:int) -> int:
            return a-c

        simulation = LambdaSimulation(2,C,A,R)

        self.assertEqual(len(simulation.interactions), 2)

class Interaction_Tests(unittest.TestCase):

    def test_constructor_no_context(self) -> None:
        Interaction(None, [1, 2])

    def test_constructor_context(self) -> None:
        Interaction((1,2,3,4), [1, 2])

    def test_context_correct_1(self) -> None:
        self.assertEqual(None, Interaction(None, [1, 2]).context)

    def test_actions_correct_1(self) -> None:
        self.assertSequenceEqual([1, 2], Interaction(None, [1, 2]).actions)

    def test_actions_correct_2(self) -> None:
        self.assertSequenceEqual(["A", "B"], Interaction(None, ["A", "B"]).actions)

    def test_actions_correct_3(self) -> None:
        self.assertSequenceEqual([(1,2), (3,4)], Interaction(None, [(1,2), (3,4)]).actions)

if __name__ == '__main__':
    unittest.main()